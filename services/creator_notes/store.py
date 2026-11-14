"""Durable SQLite storage for creator notes, revisions, challenges and sessions."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .models import CreatorResearchNote


class CreatorNotesStoreError(RuntimeError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CreatorNotesStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS creator_notes (
                    note_id TEXT PRIMARY KEY,
                    creator_account TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    current_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT,
                    withdrawn_at TEXT,
                    withdrawal_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_creator_notes_public
                    ON creator_notes(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_creator_notes_creator
                    ON creator_notes(creator_account, updated_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_notes_published_digest
                    ON creator_notes(creator_account, content_digest, status)
                    WHERE status = 'PUBLISHED';

                CREATE TABLE IF NOT EXISTS creator_note_revisions (
                    note_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    creator_account TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(note_id, revision),
                    FOREIGN KEY(note_id) REFERENCES creator_notes(note_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS creator_auth_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    nonce_b64 TEXT NOT NULL,
                    message TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_creator_auth_challenges_account
                    ON creator_auth_challenges(account_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS creator_auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_creator_auth_sessions_account
                    ON creator_auth_sessions(account_id, expires_at);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------
    # Notes and immutable revision history
    # ------------------------------------------------------------------
    def create_note(self, note: CreatorResearchNote) -> CreatorResearchNote:
        with self._lock, self._db:
            try:
                self._db.execute(
                    """
                    INSERT INTO creator_notes
                    (note_id, creator_account, status, revision, content_digest,
                     evidence_digest, current_json, created_at, updated_at,
                     published_at, withdrawn_at, withdrawal_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note.note_id,
                        note.creator_account,
                        note.status,
                        note.revision,
                        note.content_digest,
                        note.evidence_digest,
                        _json(note.to_dict()),
                        note.created_at,
                        note.updated_at,
                        note.published_at,
                        note.withdrawn_at,
                        note.withdrawal_reason,
                    ),
                )
                self._insert_revision(note)
            except sqlite3.IntegrityError as exc:
                raise CreatorNotesStoreError("note already exists or duplicates a published note") from exc
        return note

    def save_revision(self, note: CreatorResearchNote) -> CreatorResearchNote:
        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE creator_notes
                SET status = ?, revision = ?, content_digest = ?, evidence_digest = ?,
                    current_json = ?, updated_at = ?, published_at = ?, withdrawn_at = ?,
                    withdrawal_reason = ?
                WHERE note_id = ?
                """,
                (
                    note.status,
                    note.revision,
                    note.content_digest,
                    note.evidence_digest,
                    _json(note.to_dict()),
                    note.updated_at,
                    note.published_at,
                    note.withdrawn_at,
                    note.withdrawal_reason,
                    note.note_id,
                ),
            )
            self._insert_revision(note)
        return note

    def _insert_revision(self, note: CreatorResearchNote) -> None:
        self._db.execute(
            """
            INSERT INTO creator_note_revisions
            (note_id, revision, creator_account, status, record_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                note.note_id,
                note.revision,
                note.creator_account,
                note.status,
                _json(note.to_dict()),
                note.updated_at,
            ),
        )

    def get_note(self, note_id: str) -> CreatorResearchNote | None:
        with self._lock:
            row = self._db.execute(
                "SELECT current_json FROM creator_notes WHERE note_id = ?", (note_id,)
            ).fetchone()
        return CreatorResearchNote.from_dict(json.loads(row["current_json"])) if row else None

    def list_notes(
        self,
        *,
        status: str | None = None,
        creator_account: str | None = None,
        limit: int = 20,
    ) -> list[CreatorResearchNote]:
        limit = max(1, min(int(limit), 50))
        clauses: list[str] = []
        args: list[Any] = []
        if status:
            clauses.append("status = ?")
            args.append(status)
        if creator_account:
            clauses.append("creator_account = ?")
            args.append(creator_account)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT current_json FROM creator_notes {where} ORDER BY updated_at DESC LIMIT ?",
                (*args, limit),
            ).fetchall()
        return [CreatorResearchNote.from_dict(json.loads(row["current_json"])) for row in rows]

    def find_published_digest(self, creator_account: str, content_digest: str) -> CreatorResearchNote | None:
        with self._lock:
            row = self._db.execute(
                """
                SELECT current_json FROM creator_notes
                WHERE creator_account = ? AND content_digest = ? AND status = 'PUBLISHED'
                LIMIT 1
                """,
                (creator_account, content_digest),
            ).fetchone()
        return CreatorResearchNote.from_dict(json.loads(row["current_json"])) if row else None

    def revisions(self, note_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT record_json FROM creator_note_revisions
                WHERE note_id = ? ORDER BY revision ASC
                """,
                (note_id,),
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    # ------------------------------------------------------------------
    # Challenge/session material. Only hashes of bearer tokens are stored.
    # ------------------------------------------------------------------
    def create_challenge(
        self,
        *,
        account_id: str,
        nonce_b64: str,
        message: str,
        recipient: str,
        created_at: str,
        expires_at: str,
    ) -> dict[str, str]:
        challenge_id = f"challenge_{uuid.uuid4().hex}"
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_auth_challenges
                (challenge_id, account_id, nonce_b64, message, recipient, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (challenge_id, account_id, nonce_b64, message, recipient, created_at, expires_at),
            )
        return {
            "challenge_id": challenge_id,
            "account_id": account_id,
            "nonce_b64": nonce_b64,
            "message": message,
            "recipient": recipient,
            "created_at": created_at,
            "expires_at": expires_at,
        }

    def get_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_auth_challenges WHERE challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return dict(row) if row else None

    def consume_challenge(self, challenge_id: str, used_at: str) -> bool:
        with self._lock, self._db:
            result = self._db.execute(
                """
                UPDATE creator_auth_challenges SET used_at = ?
                WHERE challenge_id = ? AND used_at IS NULL
                """,
                (used_at, challenge_id),
            )
        return result.rowcount == 1

    def create_session(
        self,
        *,
        account_id: str,
        public_key: str,
        created_at: str,
        expires_at: str,
    ) -> str:
        token = secrets.token_urlsafe(48)
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_auth_sessions
                (token_hash, account_id, public_key, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_token_hash(token), account_id, public_key, created_at, expires_at, created_at),
            )
        return token

    def get_session(self, token: str, now: str) -> dict[str, Any] | None:
        token_hash = _token_hash(token)
        with self._lock, self._db:
            row = self._db.execute(
                """
                SELECT * FROM creator_auth_sessions
                WHERE token_hash = ? AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if row:
                self._db.execute(
                    "UPDATE creator_auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (now, token_hash),
                )
        return dict(row) if row else None

    def count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) AS count FROM creator_notes").fetchone()
        return int(row["count"])
