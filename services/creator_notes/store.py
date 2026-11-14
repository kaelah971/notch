"""Durable SQLite storage for creator notes, revisions, challenges and sessions."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
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


def _parse_utc_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
                    payment_kind TEXT NOT NULL DEFAULT 'ONE_TIME',
                    plan_id TEXT,
                    plan_version INTEGER,
                    subscription_id TEXT,
                    terms_json TEXT,
                    correlation_id TEXT,
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

                CREATE TABLE IF NOT EXISTS creator_subscription_plans (
                    plan_id TEXT PRIMARY KEY,
                    creator_account TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    current_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_creator_subscription_plans_public
                    ON creator_subscription_plans(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_creator_subscription_plans_creator
                    ON creator_subscription_plans(creator_account, updated_at DESC);

                CREATE TABLE IF NOT EXISTS creator_subscription_plan_versions (
                    plan_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    creator_account TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(plan_id, version),
                    FOREIGN KEY(plan_id) REFERENCES creator_subscription_plans(plan_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS creator_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    subscriber_account TEXT NOT NULL,
                    creator_account TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    renewal_cancelled INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    expires_at TEXT,
                    current_plan_version INTEGER,
                    last_payment_intent_id TEXT,
                    last_tx_hash TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(subscriber_account, plan_id),
                    FOREIGN KEY(plan_id) REFERENCES creator_subscription_plans(plan_id)
                );
                CREATE INDEX IF NOT EXISTS idx_creator_subscriptions_subscriber
                    ON creator_subscriptions(subscriber_account, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_creator_subscriptions_creator
                    ON creator_subscriptions(creator_account, updated_at DESC);

                CREATE TABLE IF NOT EXISTS creator_subscription_payments (
                    payment_id TEXT PRIMARY KEY,
                    subscription_id TEXT NOT NULL,
                    payment_intent_id TEXT NOT NULL UNIQUE,
                    tx_hash TEXT NOT NULL UNIQUE,
                    receipt_id TEXT NOT NULL,
                    plan_version INTEGER NOT NULL,
                    amount_base_units TEXT NOT NULL,
                    token_contract TEXT NOT NULL,
                    term_started_at TEXT NOT NULL,
                    term_expires_at TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    terms_json TEXT NOT NULL,
                    FOREIGN KEY(subscription_id) REFERENCES creator_subscriptions(subscription_id)
                );
                CREATE INDEX IF NOT EXISTS idx_creator_subscription_payments_subscription
                    ON creator_subscription_payments(subscription_id, granted_at DESC);
                """
            )
            payment_columns = {row[1] for row in self._db.execute("PRAGMA table_info(creator_payment_intents)").fetchall()}
            if "payment_kind" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN payment_kind TEXT NOT NULL DEFAULT 'ONE_TIME'")
            if "plan_id" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN plan_id TEXT")
            if "plan_version" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN plan_version INTEGER")
            if "subscription_id" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN subscription_id TEXT")
            if "terms_json" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN terms_json TEXT")
            if "correlation_id" not in payment_columns:
                self._db.execute("ALTER TABLE creator_payment_intents ADD COLUMN correlation_id TEXT")
            self._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_creator_payment_intents_correlation ON creator_payment_intents(correlation_id) WHERE correlation_id IS NOT NULL")
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
                     expires_at, updated_at, payment_kind, plan_id, plan_version,
                     subscription_id, terms_json, correlation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["intent_id"], record["buyer_account"], record["creator_account"],
                        record["note_id"], int(record["note_revision"]), record["content_digest"],
                        record["token_contract"], record["token_symbol"], int(record["token_decimals"]),
                        record["amount_base_units"], record["recipient_account"], record["memo"],
                        record["status"], record["created_at"], record["expires_at"], record["updated_at"],
                        record.get("payment_kind", "ONE_TIME"), record.get("plan_id"), record.get("plan_version"),
                        record.get("subscription_id"), record.get("terms_json"), record.get("correlation_id"),
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
    # Subscription plans, subscriptions and verified term payments.
    # ------------------------------------------------------------------
    def create_subscription_plan(self, record: dict[str, Any], version_record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            self._db.execute(
                """
                INSERT INTO creator_subscription_plans
                (plan_id, creator_account, status, current_version, current_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["plan_id"], record["creator_account"], record["status"],
                    int(record["current_version"]), _json(record), record["created_at"], record["updated_at"],
                ),
            )
            self._db.execute(
                """
                INSERT INTO creator_subscription_plan_versions
                (plan_id, version, creator_account, record_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    version_record["plan_id"], int(version_record["version"]), version_record["creator_account"],
                    _json(version_record), version_record["created_at"],
                ),
            )
        return self.get_subscription_plan(str(record["plan_id"])) or dict(record)

    def get_subscription_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_subscription_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_subscription_plans(
        self, *, creator_account: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if creator_account:
            clauses.append("creator_account = ?")
            args.append(creator_account)
        if status:
            clauses.append("status = ?")
            args.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM creator_subscription_plans {where} ORDER BY updated_at DESC LIMIT ?",
                (*args, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_subscription_plan(
        self, record: dict[str, Any], version_record: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE creator_subscription_plans
                SET status = ?, current_version = ?, current_json = ?, updated_at = ?
                WHERE plan_id = ?
                """,
                (
                    record["status"], int(record["current_version"]), _json(record),
                    record["updated_at"], record["plan_id"],
                ),
            )
            if version_record is not None:
                self._db.execute(
                    """
                    INSERT INTO creator_subscription_plan_versions
                    (plan_id, version, creator_account, record_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        version_record["plan_id"], int(version_record["version"]), version_record["creator_account"],
                        _json(version_record), version_record["created_at"],
                    ),
                )
        return self.get_subscription_plan(str(record["plan_id"])) or dict(record)

    def list_subscription_plan_versions(self, plan_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT record_json FROM creator_subscription_plan_versions WHERE plan_id = ? ORDER BY version ASC",
                (plan_id,),
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    def create_subscription(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._db:
            try:
                self._db.execute(
                    """
                    INSERT INTO creator_subscriptions
                    (subscription_id, subscriber_account, creator_account, plan_id, status,
                     renewal_cancelled, started_at, expires_at, current_plan_version,
                     last_payment_intent_id, last_tx_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["subscription_id"], record["subscriber_account"], record["creator_account"],
                        record["plan_id"], record.get("status", "PENDING"),
                        1 if record.get("renewal_cancelled") else 0, record.get("started_at"),
                        record.get("expires_at"), record.get("current_plan_version"),
                        record.get("last_payment_intent_id"), record.get("last_tx_hash"),
                        record["created_at"], record["updated_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._db.execute(
                    "SELECT * FROM creator_subscriptions WHERE subscriber_account = ? AND plan_id = ?",
                    (record["subscriber_account"], record["plan_id"]),
                ).fetchone()
                if not existing:
                    raise
                return dict(existing)
        return self.get_subscription(str(record["subscription_id"])) or dict(record)

    def get_subscription(self, subscription_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_subscriptions WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["renewal_cancelled"] = bool(value["renewal_cancelled"])
        return value

    def get_subscription_for_plan(self, subscriber_account: str, plan_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM creator_subscriptions WHERE subscriber_account = ? AND plan_id = ?",
                (subscriber_account, plan_id),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["renewal_cancelled"] = bool(value["renewal_cancelled"])
        return value

    def list_subscriptions(
        self, *, subscriber_account: str | None = None, creator_account: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if subscriber_account:
            clauses.append("subscriber_account = ?")
            args.append(subscriber_account)
        if creator_account:
            clauses.append("creator_account = ?")
            args.append(creator_account)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM creator_subscriptions {where} ORDER BY updated_at DESC LIMIT ?",
                (*args, max(1, min(int(limit), 100))),
            ).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            item["renewal_cancelled"] = bool(item["renewal_cancelled"])
            values.append(item)
        return values

    def get_latest_subscription_payment_intent(self, subscription_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                """
                SELECT * FROM creator_payment_intents
                WHERE subscription_id = ? AND payment_kind = 'SUBSCRIPTION'
                ORDER BY created_at DESC LIMIT 1
                """,
                (subscription_id,),
            ).fetchone()
        return dict(row) if row else None

    def cancel_subscription(self, subscription_id: str, updated_at: str) -> dict[str, Any] | None:
        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE creator_subscriptions
                SET renewal_cancelled = 1, status = CASE WHEN expires_at IS NULL THEN 'CANCELLED' ELSE status END,
                    updated_at = ?
                WHERE subscription_id = ?
                """,
                (updated_at, subscription_id),
            )
        return self.get_subscription(subscription_id)

    def mark_subscription_payment_failed(self, subscription_id: str, updated_at: str) -> dict[str, Any] | None:
        with self._lock, self._db:
            self._db.execute(
                """
                UPDATE creator_subscriptions
                SET status = CASE WHEN started_at IS NULL THEN 'FAILED' ELSE status END,
                    updated_at = ?
                WHERE subscription_id = ?
                """,
                (updated_at, subscription_id),
            )
        return self.get_subscription(subscription_id)

    def apply_subscription_payment(
        self,
        *,
        subscription_id: str,
        payment_intent: dict[str, Any],
        tx_hash: str,
        receipt_id: str,
        now_iso: str,
        duration_days: int,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                subscription_row = self._db.execute(
                    "SELECT * FROM creator_subscriptions WHERE subscription_id = ?",
                    (subscription_id,),
                ).fetchone()
                if not subscription_row:
                    raise CreatorNotesStoreError("subscription was not found")
                existing_payment = self._db.execute(
                    "SELECT * FROM creator_subscription_payments WHERE payment_intent_id = ?",
                    (payment_intent["intent_id"],),
                ).fetchone()
                if existing_payment:
                    self._db.commit()
                    return {"created": False, "reason": "IDEMPOTENT", "subscription": dict(subscription_row), "payment": dict(existing_payment)}
                tx_payment = self._db.execute(
                    "SELECT * FROM creator_subscription_payments WHERE tx_hash = ?",
                    (tx_hash,),
                ).fetchone()
                if tx_payment:
                    self._db.commit()
                    return {"created": False, "reason": "DUPLICATE_TX", "subscription": dict(subscription_row), "payment": dict(tx_payment)}
                now = _parse_utc_iso(now_iso)
                current_expiry = _parse_utc_iso(subscription_row["expires_at"])
                start = current_expiry if current_expiry and current_expiry > now else now
                expiry = start + timedelta(days=int(duration_days))
                payment = {
                    "payment_id": f"subscription_payment_{uuid.uuid4().hex}",
                    "subscription_id": subscription_id,
                    "payment_intent_id": payment_intent["intent_id"],
                    "tx_hash": tx_hash,
                    "receipt_id": receipt_id,
                    "plan_version": int(payment_intent["plan_version"]),
                    "amount_base_units": payment_intent["amount_base_units"],
                    "token_contract": payment_intent["token_contract"],
                    "term_started_at": _iso_utc(start),
                    "term_expires_at": _iso_utc(expiry),
                    "granted_at": now_iso,
                    "terms_json": payment_intent.get("terms_json") or "{}",
                }
                self._db.execute(
                    """
                    INSERT INTO creator_subscription_payments
                    (payment_id, subscription_id, payment_intent_id, tx_hash, receipt_id,
                     plan_version, amount_base_units, token_contract, term_started_at,
                     term_expires_at, granted_at, terms_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payment["payment_id"], payment["subscription_id"], payment["payment_intent_id"],
                        payment["tx_hash"], payment["receipt_id"], payment["plan_version"],
                        payment["amount_base_units"], payment["token_contract"], payment["term_started_at"],
                        payment["term_expires_at"], payment["granted_at"], payment["terms_json"],
                    ),
                )
                self._db.execute(
                    """
                    UPDATE creator_subscriptions
                    SET status = 'ACTIVE', renewal_cancelled = 0, started_at = COALESCE(started_at, ?),
                        expires_at = ?, current_plan_version = ?, last_payment_intent_id = ?,
                        last_tx_hash = ?, updated_at = ?
                    WHERE subscription_id = ?
                    """,
                    (
                        payment["term_started_at"], payment["term_expires_at"], payment["plan_version"],
                        payment["payment_intent_id"], payment["tx_hash"], now_iso, subscription_id,
                    ),
                )
                self._db.commit()
                updated = self._db.execute(
                    "SELECT * FROM creator_subscriptions WHERE subscription_id = ?",
                    (subscription_id,),
                ).fetchone()
                result_subscription = dict(updated) if updated else dict(subscription_row)
                result_subscription["renewal_cancelled"] = bool(result_subscription.get("renewal_cancelled"))
                return {"created": True, "reason": "CREATED", "subscription": result_subscription, "payment": payment}
            except Exception:
                self._db.rollback()
                raise

    def list_subscription_payments(self, subscription_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM creator_subscription_payments WHERE subscription_id = ? ORDER BY granted_at DESC",
                (subscription_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_active_subscriptions(self, creator_account: str, now_iso: str) -> int:
        with self._lock:
            row = self._db.execute(
                """
                SELECT COUNT(*) AS count FROM creator_subscriptions
                WHERE creator_account = ? AND started_at IS NOT NULL AND expires_at > ?
                """,
                (creator_account, now_iso),
            ).fetchone()
        return int(row["count"] if row else 0)

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
