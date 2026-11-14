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
                    used_at TEXT,
                    network TEXT NOT NULL DEFAULT 'testnet'
                );
                CREATE INDEX IF NOT EXISTS idx_creator_auth_challenges_account
                    ON creator_auth_challenges(account_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS creator_auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    network TEXT NOT NULL DEFAULT 'testnet',
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_creator_auth_sessions_account
                    ON creator_auth_sessions(account_id, expires_at);

                CREATE TABLE IF NOT EXISTS creator_payout_accounts (
                    creator_account TEXT PRIMARY KEY,
                    payout_account TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    token_contract TEXT NOT NULL,
                    token_symbol TEXT NOT NULL,
                    token_decimals INTEGER NOT NULL,
                    storage_registered INTEGER NOT NULL,
                    verified_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS creator_payment_intents (
                    intent_id TEXT PRIMARY KEY,
                    buyer_account TEXT NOT NULL,
                    creator_account TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    note_revision INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    token_contract TEXT NOT NULL,
                    token_symbol TEXT NOT NULL,
                    token_decimals INTEGER NOT NULL,
                    amount_base_units TEXT NOT NULL,
                    recipient_account TEXT NOT NULL,
                    memo TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    tx_hash TEXT,
                    receipt_id TEXT,
                    failure_code TEXT,
                    failure_message TEXT,
                    FOREIGN KEY(note_id) REFERENCES creator_notes(note_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_payment_intents_tx
                    ON creator_payment_intents(tx_hash)
                    WHERE tx_hash IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_creator_payment_intents_buyer
                    ON creator_payment_intents(buyer_account, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_creator_payment_intents_creator
                    ON creator_payment_intents(creator_account, created_at DESC);

                CREATE TABLE IF NOT EXISTS creator_entitlements (
                    entitlement_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL UNIQUE,
                    buyer_account TEXT NOT NULL,
                    creator_account TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    note_revision INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    tx_hash TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    FOREIGN KEY(intent_id) REFERENCES creator_payment_intents(intent_id),
                    FOREIGN KEY(note_id) REFERENCES creator_notes(note_id),
                    UNIQUE(buyer_account, note_id, note_revision)
                );
                CREATE INDEX IF NOT EXISTS idx_creator_entitlements_buyer
                    ON creator_entitlements(buyer_account, granted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_creator_entitlements_creator
                    ON creator_entitlements(creator_account, granted_at DESC);
                """
            )
            challenge_columns = {row[1] for row in self._db.execute("PRAGMA table_info(creator_auth_challenges)").fetchall()}
            if "network" not in challenge_columns:
                self._db.execute("ALTER TABLE creator_auth_challenges ADD COLUMN network TEXT NOT NULL DEFAULT 'testnet'")
            session_columns = {row[1] for row in self._db.execute("PRAGMA table_info(creator_auth_sessions)").fetchall()}
            if "network" not in session_columns:
                self._db.execute("ALTER TABLE creator_auth_sessions ADD COLUMN network TEXT NOT NULL DEFAULT 'testnet'")
            if "revoked_at" not in session_columns:
                self._db.execute("ALTER TABLE creator_auth_sessions ADD COLUMN revoked_at TEXT")

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

    def get_revision(self, note_id: str, revision: int) -> CreatorResearchNote | None:
        with self._lock:
            row = self._db.execute(
                """
                SELECT record_json FROM creator_note_revisions
                WHERE note_id = ? AND revision = ?
                """,
                (note_id, int(revision)),
            ).fetchone()
        return CreatorResearchNote.from_dict(json.loads(row["record_json"])) if row else None

    # ------------------------------------------------------------------
    # Payout, payment intents and entitlements.
    # ------------------------------------------------------------------
    def save_payout_account(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_payout_accounts
                (creator_account, payout_account, public_key, token_contract,
                 token_symbol, token_decimals, storage_registered, verified_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(creator_account) DO UPDATE SET
                    payout_account = excluded.payout_account,
                    public_key = excluded.public_key,
                    token_contract = excluded.token_contract,
                    token_symbol = excluded.token_symbol,
                    token_decimals = excluded.token_decimals,
                    storage_registered = excluded.storage_registered,
                    verified_at = excluded.verified_at,
                    updated_at = excluded.updated_at
                """,
                (
                    record["creator_account"],
                    record["payout_account"],
                    record["public_key"],
                    record["token_contract"],
                    record["token_symbol"],
                    int(record["token_decimals"]),
                    1 if record["storage_registered"] else 0,
                    record["verified_at"],
                    record["updated_at"],
                ),
            )
        return self.get_payout_account(str(record["creator_account"])) or dict(record)

    def get_payout_account(self, creator_account: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_payout_accounts WHERE creator_account = ?",
                (creator_account,),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["storage_registered"] = bool(value["storage_registered"])
        return value

    def create_payment_intent(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            try:
                self._db.execute(
                    """
                    INSERT INTO creator_payment_intents
                    (intent_id, buyer_account, creator_account, note_id, note_revision,
                     content_digest, token_contract, token_symbol, token_decimals,
                     amount_base_units, recipient_account, memo, status, created_at,
                     expires_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["intent_id"], record["buyer_account"], record["creator_account"],
                        record["note_id"], int(record["note_revision"]), record["content_digest"],
                        record["token_contract"], record["token_symbol"], int(record["token_decimals"]),
                        record["amount_base_units"], record["recipient_account"], record["memo"],
                        record["status"], record["created_at"], record["expires_at"], record["updated_at"],
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CreatorNotesStoreError("payment intent already exists or memo is already used") from exc
        return self.get_payment_intent(str(record["intent_id"])) or dict(record)

    def get_payment_intent(self, intent_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_payment_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
        return dict(row) if row else None

    def find_payment_intent_by_tx(self, tx_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_payment_intents WHERE tx_hash = ? LIMIT 1",
                (tx_hash,),
            ).fetchone()
        return dict(row) if row else None

    def update_payment_intent(self, intent_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "status", "updated_at", "tx_hash", "receipt_id", "failure_code", "failure_message",
        }
        fields = [(key, value) for key, value in changes.items() if key in allowed]
        if not fields:
            return self.get_payment_intent(intent_id)
        assignments = ", ".join(f"{key} = ?" for key, _ in fields)
        with self._lock, self._db:
            self._db.execute(
                f"UPDATE creator_payment_intents SET {assignments} WHERE intent_id = ?",
                (*[value for _, value in fields], intent_id),
            )
        return self.get_payment_intent(intent_id)

    def create_entitlement(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            try:
                self._db.execute(
                    """
                    INSERT INTO creator_entitlements
                    (entitlement_id, intent_id, buyer_account, creator_account, note_id,
                     note_revision, content_digest, tx_hash, receipt_id, granted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["entitlement_id"], record["intent_id"], record["buyer_account"],
                        record["creator_account"], record["note_id"], int(record["note_revision"]),
                        record["content_digest"], record["tx_hash"], record["receipt_id"], record["granted_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._db.execute(
                    "SELECT * FROM creator_entitlements WHERE intent_id = ? OR (buyer_account = ? AND note_id = ? AND note_revision = ?)",
                    (record["intent_id"], record["buyer_account"], record["note_id"], int(record["note_revision"])),
                ).fetchone()
                if not existing:
                    raise
                return dict(existing)
        return self.get_entitlement(str(record["entitlement_id"])) or dict(record)

    def get_entitlement(self, entitlement_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_entitlements WHERE entitlement_id = ?",
                (entitlement_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_entitlement_for_note(
        self, buyer_account: str, note_id: str, revision: int | None = None
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM creator_entitlements WHERE buyer_account = ? AND note_id = ?"
        args: list[Any] = [buyer_account, note_id]
        if revision is not None:
            query += " AND note_revision = ?"
            args.append(int(revision))
        query += " ORDER BY note_revision DESC, granted_at DESC LIMIT 1"
        with self._lock:
            row = self._db.execute(query, tuple(args)).fetchone()
        return dict(row) if row else None

    def list_entitlements(
        self, *, buyer_account: str | None = None, creator_account: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if buyer_account:
            clauses.append("buyer_account = ?")
            args.append(buyer_account)
        if creator_account:
            clauses.append("creator_account = ?")
            args.append(creator_account)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM creator_entitlements {where} ORDER BY granted_at DESC LIMIT ?",
                (*args, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

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
        network: str = "testnet",
    ) -> dict[str, str]:
        challenge_id = f"challenge_{uuid.uuid4().hex}"
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_auth_challenges
                (challenge_id, account_id, nonce_b64, message, recipient, created_at, expires_at, network)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (challenge_id, account_id, nonce_b64, message, recipient, created_at, expires_at, network),
            )
        return {
            "challenge_id": challenge_id,
            "account_id": account_id,
            "nonce_b64": nonce_b64,
            "message": message,
            "recipient": recipient,
            "created_at": created_at,
            "expires_at": expires_at,
            "network": network,
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
        network: str = "testnet",
    ) -> str:
        token = secrets.token_urlsafe(48)
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_auth_sessions
                (token_hash, account_id, public_key, created_at, expires_at, last_seen_at, network, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (_token_hash(token), account_id, public_key, created_at, expires_at, created_at, network),
            )
        return token

    def get_session(self, token: str, now: str) -> dict[str, Any] | None:
        token_hash = _token_hash(token)
        with self._lock, self._db:
            row = self._db.execute(
                """
                SELECT * FROM creator_auth_sessions
                WHERE token_hash = ? AND expires_at > ? AND revoked_at IS NULL
                """,
                (token_hash, now),
            ).fetchone()
            if row:
                self._db.execute(
                    "UPDATE creator_auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (now, token_hash),
                )
        return dict(row) if row else None

    def revoke_session(self, token: str, revoked_at: str) -> bool:
        with self._lock, self._db:
            result = self._db.execute(
                "UPDATE creator_auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (revoked_at, _token_hash(token)),
            )
        return result.rowcount == 1

    def count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) AS count FROM creator_notes").fetchone()
        return int(row["count"])
