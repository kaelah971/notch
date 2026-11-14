"""Durable local storage for S4 funding quotes, deposits and status events."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import FundingQuote


SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_quotes (
    quote_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    state TEXT NOT NULL,
    dry INTEGER NOT NULL,
    deposit_address TEXT,
    deposit_tx_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_funding_deposit_tx
    ON funding_quotes(deposit_tx_hash)
    WHERE deposit_tx_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_funding_state
    ON funding_quotes(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_funding_deposit_address
    ON funding_quotes(deposit_address);

CREATE TABLE IF NOT EXISTS funding_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id TEXT NOT NULL,
    event TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_funding_events_quote
    ON funding_events(quote_id, id);
"""


class FundingStoreError(RuntimeError):
    pass


class QuoteNotFoundError(FundingStoreError):
    pass


class DuplicateDepositError(FundingStoreError):
    pass


class FundingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def save_quote(self, quote: FundingQuote) -> FundingQuote:
        with self._lock, self.conn:
            self._write_quote_row(quote)
        return quote

    def _write_quote_row(self, quote: FundingQuote) -> None:
        payload = json.dumps(quote.to_storage_dict(), ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            """
            INSERT INTO funding_quotes(
                quote_id, correlation_id, state, dry, deposit_address,
                deposit_tx_hash, created_at, updated_at, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quote_id) DO UPDATE SET
                correlation_id=excluded.correlation_id,
                state=excluded.state,
                dry=excluded.dry,
                deposit_address=excluded.deposit_address,
                deposit_tx_hash=excluded.deposit_tx_hash,
                updated_at=excluded.updated_at,
                record_json=excluded.record_json
            """,
            (
                quote.quote_id,
                quote.correlation_id,
                quote.state.value,
                1 if quote.dry else 0,
                quote.deposit_address,
                quote.deposit_tx_hash,
                quote.created_at,
                quote.updated_at,
                payload,
            ),
        )

    def get_quote(self, quote_id: str) -> FundingQuote | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT record_json FROM funding_quotes WHERE quote_id=?",
                (quote_id,),
            ).fetchone()
        if not row:
            return None
        return FundingQuote.from_dict(json.loads(row["record_json"]))

    def require_quote(self, quote_id: str) -> FundingQuote:
        quote = self.get_quote(quote_id)
        if quote is None:
            raise QuoteNotFoundError(f"unknown funding quote: {quote_id}")
        return quote

    def find_by_deposit_address(self, deposit_address: str) -> FundingQuote | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT record_json FROM funding_quotes WHERE deposit_address=? "
                "ORDER BY created_at DESC LIMIT 1",
                (deposit_address,),
            ).fetchone()
        if not row:
            return None
        return FundingQuote.from_dict(json.loads(row["record_json"]))

    def find_by_deposit_tx(self, tx_hash: str) -> FundingQuote | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT record_json FROM funding_quotes WHERE deposit_tx_hash=? LIMIT 1",
                (tx_hash,),
            ).fetchone()
        if not row:
            return None
        return FundingQuote.from_dict(json.loads(row["record_json"]))

    def list_quotes(self, *, limit: int = 50) -> list[FundingQuote]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT record_json FROM funding_quotes ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [FundingQuote.from_dict(json.loads(row["record_json"])) for row in rows]

    def record_deposit(
        self,
        quote_id: str,
        tx_hash: str,
        *,
        recorded_at: str,
        submitted: bool,
    ) -> FundingQuote:
        tx_hash = tx_hash.strip()
        if not tx_hash:
            raise FundingStoreError("deposit transaction hash is required")
        with self._lock, self.conn:
            row = self.conn.execute(
                "SELECT record_json FROM funding_quotes WHERE quote_id=?",
                (quote_id,),
            ).fetchone()
            if not row:
                raise QuoteNotFoundError(f"unknown funding quote: {quote_id}")
            quote = FundingQuote.from_dict(json.loads(row["record_json"]))
            if quote.deposit_tx_hash and quote.deposit_tx_hash != tx_hash:
                raise DuplicateDepositError(
                    f"quote {quote_id} already tracks deposit {quote.deposit_tx_hash}"
                )
            existing = self.conn.execute(
                "SELECT quote_id FROM funding_quotes WHERE deposit_tx_hash=? AND quote_id<>?",
                (tx_hash, quote_id),
            ).fetchone()
            if existing:
                raise DuplicateDepositError(
                    f"deposit {tx_hash} is already tracked by quote {existing['quote_id']}"
                )
            if not quote.deposit_tx_hash:
                quote.deposit_tx_hash = tx_hash
                quote.deposit_recorded_at = recorded_at
                quote.deposit_submitted = bool(submitted)
                quote.updated_at = recorded_at
                self._write_quote_row(quote)
                self._event(
                    quote_id,
                    "deposit_recorded",
                    {
                        "tx_hash": tx_hash,
                        "submitted": bool(submitted),
                        "recorded_at": recorded_at,
                    },
                    recorded_at,
                )
            elif submitted and not quote.deposit_submitted:
                quote.deposit_submitted = True
                quote.updated_at = recorded_at
                self._write_quote_row(quote)
                self._event(
                    quote_id,
                    "deposit_submitted",
                    {"tx_hash": tx_hash, "recorded_at": recorded_at},
                    recorded_at,
                )
        return self.require_quote(quote_id)

    def append_event(
        self, quote_id: str, event: str, data: dict[str, Any], *, created_at: str
    ) -> None:
        with self._lock, self.conn:
            self._event(quote_id, event, data, created_at)

    def _event(
        self, quote_id: str, event: str, data: dict[str, Any], created_at: str
    ) -> None:
        self.conn.execute(
            "INSERT INTO funding_events(quote_id, event, data_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                quote_id,
                event,
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )

    def list_events(self, quote_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT event, data_json, created_at FROM funding_events "
                "WHERE quote_id=? ORDER BY id ASC",
                (quote_id,),
            ).fetchall()
        return [
            {
                "event": row["event"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
