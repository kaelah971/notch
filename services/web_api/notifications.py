"""Wallet-scoped, read-only notification reconciliation for resolved markets."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from services.intents.validation import is_near_account
from services.trend_radar.models import iso_utc, now_utc
from services.web_api.predictions import classify_prediction


NOTIFICATION_TYPES = frozenset({"MARKET_RESOLVED", "CLAIM_READY", "REFUND_READY"})


class NotificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class NotificationCandidate:
    account_id: str
    notification_type: str
    market_id: str
    title: str
    body: str
    href: str
    created_at: str
    dedupe_key: str
    outcome: str | None
    prediction_status: str | None
    amount: str | None
    provenance: dict[str, Any]

    @property
    def notification_id(self) -> str:
        digest = hashlib.sha256(self.dedupe_key.encode("utf-8")).hexdigest()[:24]
        return f"notification_{digest}"

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.notification_id,
            self.account_id,
            self.notification_type,
            self.market_id,
            self.title,
            self.body,
            self.href,
            self.created_at,
            self.dedupe_key,
            self.outcome,
            self.prediction_status,
            self.amount,
            self.provenance.get("finality"),
            self.provenance.get("observed_at"),
            self.provenance.get("market_block_height"),
            self.provenance.get("market_block_hash"),
            self.provenance.get("position_block_height"),
            self.provenance.get("position_block_hash"),
        )


class NotificationStore:
    """Small durable SQLite store; all reads and writes are account-scoped."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                notification_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                market_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                href TEXT NOT NULL,
                created_at TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                outcome TEXT,
                prediction_status TEXT,
                amount TEXT,
                finality TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                market_block_height INTEGER,
                market_block_hash TEXT,
                position_block_height INTEGER,
                position_block_hash TEXT,
                read_at TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS notifications_account_created "
            "ON notifications(account_id, created_at DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS notifications_account_unread "
            "ON notifications(account_id, read_at)"
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_if_absent(self, candidate: NotificationCandidate) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO notifications(
                    notification_id, account_id, notification_type, market_id,
                    title, body, href, created_at, dedupe_key, outcome,
                    prediction_status, amount, finality, observed_at,
                    market_block_height, market_block_hash,
                    position_block_height, position_block_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                candidate.to_row(),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def list_for_account(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM notifications
                WHERE account_id = ?
                ORDER BY created_at DESC, notification_id DESC
                LIMIT ?
                """,
                (account_id, bounded),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def unread_count(self, account_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE account_id = ? AND read_at IS NULL",
                (account_id,),
            ).fetchone()
        return int(row["count"] if row else 0)

    def mark_read(self, account_id: str, notification_id: str, read_at: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE notifications SET read_at = COALESCE(read_at, ?)
                WHERE account_id = ? AND notification_id = ?
                """,
                (read_at, account_id, notification_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def mark_all_read(self, account_id: str, read_at: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE notifications SET read_at = COALESCE(read_at, ?)
                WHERE account_id = ? AND read_at IS NULL
                """,
                (read_at, account_id),
            )
            self._conn.commit()
            return int(cursor.rowcount)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "notification_id": row["notification_id"],
        "type": row["notification_type"],
        "market_id": row["market_id"],
        "title": row["title"],
        "body": row["body"],
        "href": row["href"],
        "created_at": row["created_at"],
        "read_at": row["read_at"],
        "unread": row["read_at"] is None,
        "outcome": row["outcome"],
        "prediction_status": row["prediction_status"],
        "amount": row["amount"],
        "provenance": {
            "finality": row["finality"],
            "observed_at": row["observed_at"],
            "market_block_height": row["market_block_height"],
            "market_block_hash": row["market_block_hash"],
            "position_block_height": row["position_block_height"],
            "position_block_hash": row["position_block_hash"],
        },
    }


def _positive(value: Any) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _has_position(position: dict[str, Any]) -> bool:
    if _positive(position.get("total_stake")):
        return True
    stakes = position.get("stakes")
    return isinstance(stakes, list) and any(_positive(stake) for stake in stakes)


def _resolved_outcome(market: dict[str, Any]) -> str | None:
    choices = market.get("choices")
    winner = market.get("winning_outcome")
    if not isinstance(choices, list) or not choices:
        return None
    try:
        winner_index = int(winner)
    except (TypeError, ValueError):
        return None
    if isinstance(winner, bool) or winner_index < 0 or winner_index >= len(choices):
        return None
    return str(market.get("winning_choice") or choices[winner_index])


def _is_voided(market: dict[str, Any]) -> bool:
    return str(market.get("status")) == "voided" and str(
        market.get("resolution_kind") or ""
    ) in {"void", "tie"}


class NotificationService:
    """Reconcile one verified wallet on return to the app.

    There is intentionally no background worker in V1. Every authenticated inbox
    read performs a bounded, finalized read-only reconciliation before returning
    durable notifications.
    """

    def __init__(
        self,
        *,
        store: NotificationStore,
        chain: Any,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.store = store
        self.chain = chain
        self.clock = clock

    def close(self) -> None:
        self.store.close()

    def inbox(self, account_id: str, *, limit: int = 50) -> dict[str, Any]:
        reconciliation = self.reconcile(account_id)
        return {
            "notifications": self.store.list_for_account(account_id, limit),
            "unread_count": self.store.unread_count(account_id),
            "reconciliation": reconciliation,
        }

    def reconcile(self, account_id: str) -> dict[str, Any]:
        if not is_near_account(account_id):
            raise NotificationError("invalid notification account")
        observed_at = iso_utc(self.clock()) or ""
        created = 0
        inspected = 0
        markets = self.chain.list_markets()
        for listed_market in markets:
            if not isinstance(listed_market, dict):
                continue
            if str(listed_market.get("status")) not in {"resolved", "voided"}:
                continue
            market, position, provenance = self._finalized_market_position(
                listed_market, account_id, observed_at
            )
            if provenance.get("finality") != "final":
                continue
            inspected += 1
            if not isinstance(market, dict) or not isinstance(position, dict):
                continue
            if not _has_position(position):
                continue
            market_id = str(market.get("market_id") or listed_market.get("market_id") or "")
            if not market_id:
                continue
            prediction = classify_prediction(market, position)
            outcome = _resolved_outcome(market)
            resolved_at = str(market.get("resolved_at") or provenance.get("observed_at") or "")
            resolution_kind = str(market.get("resolution_kind") or "")
            if str(market.get("status")) == "resolved" and outcome is not None:
                created += self._insert(
                    NotificationCandidate(
                        account_id=account_id,
                        notification_type="MARKET_RESOLVED",
                        market_id=market_id,
                        title="Prediction resolved",
                        body=(
                            f"{market_id} resolved {outcome}. "
                            f"Your recorded call: {prediction['status']}."
                        ),
                        href=f"/app/markets/{market_id}",
                        created_at=observed_at,
                        dedupe_key=f"{account_id}:MARKET_RESOLVED:{market_id}:{resolved_at}:{outcome}",
                        outcome=outcome,
                        prediction_status=prediction["status"],
                        amount=None,
                        provenance=provenance,
                    )
                )
                if str(position.get("claim_state")) == "claimable" and _positive(position.get("claimable")):
                    amount = str(position.get("claimable"))
                    created += self._insert(
                        NotificationCandidate(
                            account_id=account_id,
                            notification_type="CLAIM_READY",
                            market_id=market_id,
                            title="Claim ready",
                            body=f"{amount} collateral base units are claimable for {market_id}.",
                            href="/app/portfolio",
                            created_at=observed_at,
                            dedupe_key=f"{account_id}:CLAIM_READY:{market_id}:{resolved_at}",
                            outcome=outcome,
                            prediction_status=prediction["status"],
                            amount=amount,
                            provenance=provenance,
                        )
                    )
            elif _is_voided(market) and str(position.get("claim_state")) == "claimable" and _positive(position.get("claimable")):
                amount = str(position.get("claimable"))
                created += self._insert(
                    NotificationCandidate(
                        account_id=account_id,
                        notification_type="REFUND_READY",
                        market_id=market_id,
                        title="Refund ready",
                        body=f"{amount} collateral base units are refundable for {market_id}.",
                        href="/app/portfolio",
                        created_at=observed_at,
                        dedupe_key=f"{account_id}:REFUND_READY:{market_id}:{resolved_at}:{resolution_kind}",
                        outcome=None,
                        prediction_status="VOIDED",
                        amount=amount,
                        provenance=provenance,
                    )
                )
        return {
            "mode": "ON_RETURN",
            "finality": "final",
            "inspected_markets": inspected,
            "created": created,
            "observed_at": observed_at,
        }

    def mark_read(self, account_id: str, notification_id: str) -> bool:
        return self.store.mark_read(
            account_id,
            notification_id,
            iso_utc(self.clock()) or "",
        )

    def mark_all_read(self, account_id: str) -> int:
        return self.store.mark_all_read(account_id, iso_utc(self.clock()) or "")

    def _insert(self, candidate: NotificationCandidate) -> int:
        return 1 if self.store.insert_if_absent(candidate) else 0

    def _finalized_market_position(
        self,
        listed_market: dict[str, Any],
        account_id: str,
        observed_at: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
        market_id = str(listed_market.get("market_id") or "")
        reader = getattr(self.chain, "get_finalized_market_position", None)
        if callable(reader):
            market, position, provenance = reader(market_id, account_id)
            result = dict(provenance or {})
            result.setdefault("finality", "final")
            result.setdefault("observed_at", observed_at)
            return market, position, result
        return (
            self.chain.get_market(market_id) or listed_market,
            self.chain.get_position(market_id, account_id),
            {
                "finality": "final",
                "observed_at": observed_at,
                "market_block_height": None,
                "market_block_hash": None,
                "position_block_height": None,
                "position_block_hash": None,
            },
        )
