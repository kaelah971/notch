"""Read-only, finalized NEAR event indexing for the public Notch Pulse view.

This module deliberately indexes only accepted ``position_entered`` events emitted by
``market_contract`` after a local tracking cursor is created (or an explicit start
height is configured). It does not sign, broadcast, or infer activity from balances,
charts, or transactions that failed.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.intents.balance import NearRpcClient, NearRpcError


EVENT_PREFIX = "EVENT_JSON:"
AMOUNT_RE = re.compile(r"^[0-9]+$")
WINDOW_SECONDS: dict[str, int | None] = {
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
    "all": None,
}


class PulseIndexError(RuntimeError):
    """The final RPC returned data that cannot be safely indexed."""


def _iso_from_ns(value: int) -> str:
    return (
        datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _canonical_amount(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    text = str(value) if isinstance(value, (int, str)) else ""
    if not AMOUNT_RE.fullmatch(text):
        return None
    normalized = str(int(text))
    return normalized if int(normalized) > 0 else None


def _successful_status(status: Any) -> bool:
    if isinstance(status, dict):
        return any(key in status for key in ("SuccessValue", "SuccessReceiptId"))
    return isinstance(status, str) and status.startswith("Success")


def _function_call(action: Any) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    value = action.get("FunctionCall")
    if value is None:
        value = action.get("function_call")
    return value if isinstance(value, dict) else None


def _decode_json_args(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _event_data_items(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, dict)]


@dataclass(frozen=True)
class PulseEvent:
    event_id: str
    tx_hash: str
    receipt_id: str
    log_index: int
    block_height: int
    block_hash: str
    block_timestamp_ns: int
    market_id: str
    account_id: str
    outcome: int
    amount_base_units: str

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.event_id,
            self.tx_hash,
            self.receipt_id,
            self.log_index,
            self.block_height,
            self.block_hash,
            self.block_timestamp_ns,
            _iso_from_ns(self.block_timestamp_ns),
            self.market_id,
            self.account_id,
            self.outcome,
            self.amount_base_units,
            "near_final_rpc",
        )


@dataclass(frozen=True)
class PulseSyncResult:
    initialized: bool
    scanned_blocks: int
    from_height: int | None
    to_height: int | None
    latest_final_height: int | None
    events_found: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "initialized": self.initialized,
            "scanned_blocks": self.scanned_blocks,
            "from_height": self.from_height,
            "to_height": self.to_height,
            "latest_final_height": self.latest_final_height,
            "events_found": self.events_found,
            "error": self.error,
        }


class PulseStore:
    """Small durable store with an atomic per-block cursor."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pulse_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pulse_events (
                event_id TEXT PRIMARY KEY,
                tx_hash TEXT NOT NULL,
                receipt_id TEXT NOT NULL,
                log_index INTEGER NOT NULL,
                block_height INTEGER NOT NULL,
                block_hash TEXT NOT NULL,
                block_timestamp_ns INTEGER NOT NULL,
                observed_at_utc TEXT NOT NULL,
                market_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                outcome INTEGER NOT NULL,
                amount_base_units TEXT NOT NULL,
                source TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS pulse_events_receipt_log
                ON pulse_events(tx_hash, receipt_id, log_index);
            CREATE INDEX IF NOT EXISTS pulse_events_time
                ON pulse_events(block_timestamp_ns DESC);
            CREATE INDEX IF NOT EXISTS pulse_events_market_time
                ON pulse_events(market_id, block_timestamp_ns DESC);
            CREATE INDEX IF NOT EXISTS pulse_events_account_time
                ON pulse_events(account_id, block_timestamp_ns DESC);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _get_meta_locked(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM pulse_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row[0]) if row else None

    def _set_meta_locked(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO pulse_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def meta(self, key: str) -> str | None:
        with self._lock:
            return self._get_meta_locked(key)

    def initialize_tracking(
        self,
        *,
        start_height: int,
        start_timestamp_ns: int,
        cursor_height: int,
        cursor_hash: str | None,
        cursor_timestamp_ns: int | None,
    ) -> None:
        with self._lock, self._conn:
            if self._get_meta_locked("coverage_start_height") is not None:
                return
            self._set_meta_locked("coverage_start_height", start_height)
            self._set_meta_locked("coverage_start_timestamp_ns", start_timestamp_ns)
            self._set_meta_locked("last_scanned_height", cursor_height)
            if cursor_hash is not None:
                self._set_meta_locked("last_scanned_hash", cursor_hash)
            if cursor_timestamp_ns is not None:
                self._set_meta_locked("last_scanned_timestamp_ns", cursor_timestamp_ns)
            self._set_meta_locked("last_error", "")

    def commit_block(
        self,
        *,
        height: int,
        block_hash: str,
        timestamp_ns: int,
        events: list[PulseEvent],
    ) -> int:
        """Insert events and advance the cursor in one SQLite transaction."""
        with self._lock, self._conn:
            inserted = 0
            for event in events:
                cursor = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO pulse_events(
                        event_id, tx_hash, receipt_id, log_index, block_height,
                        block_hash, block_timestamp_ns, observed_at_utc, market_id,
                        account_id, outcome, amount_base_units, source
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    event.to_row(),
                )
                inserted += max(cursor.rowcount, 0)
            self._set_meta_locked("last_scanned_height", height)
            self._set_meta_locked("last_scanned_hash", block_hash)
            self._set_meta_locked("last_scanned_timestamp_ns", timestamp_ns)
            self._set_meta_locked("last_error", "")
            return inserted

    def record_sync_error(self, message: str) -> None:
        with self._lock, self._conn:
            self._set_meta_locked("last_error", message[:500])

    def clear_error(self) -> None:
        with self._lock, self._conn:
            self._set_meta_locked("last_error", "")

    def cursor_height(self) -> int | None:
        value = self.meta("last_scanned_height")
        return int(value) if value is not None else None

    def _coverage_locked(self) -> dict[str, Any]:
        start_height = self._get_meta_locked("coverage_start_height")
        start_ts = self._get_meta_locked("coverage_start_timestamp_ns")
        last_height = self._get_meta_locked("last_scanned_height")
        last_ts = self._get_meta_locked("last_scanned_timestamp_ns")
        latest_height = self._get_meta_locked("latest_final_height")
        latest_ts = self._get_meta_locked("latest_final_timestamp_ns")
        last_error = self._get_meta_locked("last_error") or None
        count = int(
            self._conn.execute("SELECT COUNT(*) FROM pulse_events").fetchone()[0]
        )
        if start_height is None:
            status = "not_started"
        elif last_error:
            status = "degraded"
        else:
            status = "tracking"
        return {
            "available": start_height is not None and not last_error,
            "status": status,
            "source": "NEAR finalized RPC receipts",
            "scope": "accepted position_entered events observed after tracking began",
            "historical_backfill": False,
            "started_at_utc": _iso_from_ns(int(start_ts)) if start_ts is not None else None,
            "start_block_height": int(start_height) if start_height is not None else None,
            "last_scanned_block_height": int(last_height) if last_height is not None else None,
            "last_scanned_at_utc": _iso_from_ns(int(last_ts)) if last_ts is not None else None,
            "latest_final_block_height": int(latest_height) if latest_height is not None else None,
            "latest_final_at_utc": _iso_from_ns(int(latest_ts)) if latest_ts is not None else None,
            "indexed_event_count": count,
            "last_error": last_error,
            "limitations": [
                "Coverage begins when this indexer's cursor is initialized.",
                "Only successful, finalized market position_entered events count.",
                "Failed transactions, rejected entries, charts, and balances are excluded.",
            ],
        }

    def set_latest_final(self, *, height: int, timestamp_ns: int) -> None:
        with self._lock, self._conn:
            self._set_meta_locked("latest_final_height", height)
            self._set_meta_locked("latest_final_timestamp_ns", timestamp_ns)
            self._set_meta_locked("last_sync_at_utc", _iso_from_ns(timestamp_ns))

    def coverage(self) -> dict[str, Any]:
        with self._lock:
            return self._coverage_locked()

    def _as_of_ns_locked(self, fallback_ns: int) -> int:
        value = self._get_meta_locked("latest_final_timestamp_ns")
        if value is None:
            value = self._get_meta_locked("last_scanned_timestamp_ns")
        return int(value) if value is not None else fallback_ns

    def summary(self, *, window: str, as_of_ns: int | None = None, limit: int = 50) -> dict[str, Any]:
        if window not in WINDOW_SECONDS:
            raise ValueError(f"unsupported Pulse window: {window}")
        now_ns = as_of_ns or int(datetime.now(tz=timezone.utc).timestamp() * 1_000_000_000)
        with self._lock:
            now_ns = self._as_of_ns_locked(now_ns)
            coverage_start = int(self._get_meta_locked("coverage_start_timestamp_ns") or 0)
            span = WINDOW_SECONDS[window]
            lower_ns = coverage_start if span is None else max(
                coverage_start, now_ns - span * 1_000_000_000
            )
            rows = self._conn.execute(
                """
                SELECT event_id, tx_hash, receipt_id, log_index, block_height,
                       block_hash, block_timestamp_ns, observed_at_utc, market_id,
                       account_id, outcome, amount_base_units, source
                FROM pulse_events
                WHERE block_timestamp_ns >= ? AND block_timestamp_ns <= ?
                ORDER BY block_timestamp_ns DESC, event_id DESC
                """,
                (lower_ns, now_ns),
            ).fetchall()
            all_first_seen = self._conn.execute(
                "SELECT account_id, MIN(block_timestamp_ns) AS first_seen "
                "FROM pulse_events GROUP BY account_id"
            ).fetchall()

        accounts: set[str] = set()
        market_positions: set[tuple[str, str]] = set()
        markets: dict[str, dict[str, Any]] = {}
        total_amount = 0
        for row in rows:
            amount = int(row["amount_base_units"])
            total_amount += amount
            account_id = str(row["account_id"])
            market_id = str(row["market_id"])
            accounts.add(account_id)
            market_positions.add((account_id, market_id))
            item = markets.setdefault(
                market_id,
                {"market_id": market_id, "amount": 0, "count": 0, "positions": set(), "accounts": set(), "last": 0},
            )
            item["amount"] += amount
            item["count"] += 1
            item["positions"].add((account_id, market_id))
            item["accounts"].add(account_id)
            item["last"] = max(item["last"], int(row["block_timestamp_ns"]))

        hot_markets = [
            {
                "market_id": item["market_id"],
                "confirmed_volume_base_units": str(item["amount"]),
                "successful_entries": len(item["positions"]),
                "successful_entry_events": item["count"],
                "forecaster_count": len(item["accounts"]),
                "last_activity_at_utc": _iso_from_ns(item["last"]),
            }
            for item in sorted(
                markets.values(),
                key=lambda value: (-value["amount"], -value["count"], value["market_id"]),
            )[:10]
        ]
        recent_calls = [
            {
                "event_id": str(row["event_id"]),
                "tx_hash": str(row["tx_hash"]),
                "receipt_id": str(row["receipt_id"]),
                "log_index": int(row["log_index"]),
                "market_id": str(row["market_id"]),
                "account_id": str(row["account_id"]),
                "outcome": int(row["outcome"]),
                "amount_base_units": str(row["amount_base_units"]),
                "block_height": int(row["block_height"]),
                "block_hash": str(row["block_hash"]),
                "observed_at_utc": str(row["observed_at_utc"]),
                "source": str(row["source"]),
                "verification": "finalized_position_entered_event",
            }
            for row in rows[: max(1, min(limit, 100))]
        ]
        new_forecasters = sum(
            1 for row in all_first_seen if lower_ns <= int(row["first_seen"]) <= now_ns
        )
        return {
            "coverage": self.coverage(),
            "as_of_utc": _iso_from_ns(now_ns),
            "window": window,
            "currency": {"symbol": "USDC", "decimals": 6, "unit": "base_units"},
            "metrics": {
                "forecaster_count": len(accounts),
                "new_forecaster_count": new_forecasters,
                "confirmed_volume_base_units": str(total_amount),
                "successful_entries": len(market_positions),
                "successful_entry_events": len(rows),
            },
            "hot_markets": hot_markets,
            "recent_calls": recent_calls,
        }


class PulseIndexer:
    """Bounded, resumable scanner over finalized NEAR blocks."""

    def __init__(
        self,
        *,
        rpc: NearRpcClient,
        store: PulseStore,
        market_contract: str,
        collateral_token: str,
        start_block: int | None = None,
        max_blocks: int = 25,
    ) -> None:
        self.rpc = rpc
        self.store = store
        self.market_contract = market_contract
        self.collateral_token = collateral_token
        self.start_block = start_block
        self.max_blocks = max(1, min(max_blocks, 500))
        self._lock = threading.Lock()

    def close(self) -> None:
        self.store.close()

    def _rpc(self, method: str, params: Any) -> Any:
        return self.rpc._rpc(method, params)

    @staticmethod
    def _header(result: Any) -> tuple[int, str, int]:
        if not isinstance(result, dict) or not isinstance(result.get("header"), dict):
            raise PulseIndexError("final RPC returned a block without a header")
        header = result["header"]
        try:
            height = int(header["height"])
            block_hash = str(header["hash"])
            timestamp_ns = int(header["timestamp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PulseIndexError("final RPC returned an invalid block header") from exc
        if height < 0 or not block_hash or timestamp_ns <= 0:
            raise PulseIndexError("final RPC returned an invalid block header")
        return height, block_hash, timestamp_ns

    def _entry_candidates(self, transaction: Any) -> list[dict[str, Any]]:
        if not isinstance(transaction, dict):
            return []
        if transaction.get("receiver_id") != self.collateral_token:
            return []
        tx_hash = transaction.get("hash")
        signer_id = transaction.get("signer_id")
        if not isinstance(tx_hash, str) or not tx_hash or not isinstance(signer_id, str) or not signer_id:
            return []
        candidates: list[dict[str, Any]] = []
        for action in transaction.get("actions", []):
            call = _function_call(action)
            if not call or call.get("method_name") != "ft_transfer_call":
                continue
            args = _decode_json_args(call.get("args"))
            if not args or args.get("receiver_id") != self.market_contract:
                continue
            amount = _canonical_amount(args.get("amount"))
            message = args.get("msg")
            if amount is None or not isinstance(message, str):
                continue
            try:
                message_obj = json.loads(message)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(message_obj, dict):
                continue
            market_id = message_obj.get("market_id")
            outcome = message_obj.get("outcome")
            if not isinstance(market_id, str) or not market_id:
                continue
            if isinstance(outcome, bool) or not isinstance(outcome, int) or outcome < 0:
                continue
            candidates.append(
                {
                    "tx_hash": tx_hash,
                    "signer_id": signer_id,
                    "market_id": market_id,
                    "outcome": outcome,
                    "amount": amount,
                }
            )
        return candidates

    def _receipt_block(self, block_hash: str) -> tuple[int, str, int]:
        result = self._rpc("block", {"block_id": block_hash})
        return self._header(result)

    def _events_for_transaction(
        self,
        transaction: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> list[PulseEvent]:
        tx_hash = str(transaction["hash"])
        signer_id = str(transaction["signer_id"])
        status = self._rpc("EXPERIMENTAL_tx_status", [tx_hash, signer_id])
        if not isinstance(status, dict) or not _successful_status(status.get("status")):
            return []
        status_tx = status.get("transaction")
        if isinstance(status_tx, dict) and status_tx.get("hash") not in (None, tx_hash):
            raise PulseIndexError("transaction status hash did not match the scanned transaction")
        events: list[PulseEvent] = []
        for receipt_outcome in status.get("receipts_outcome", []):
            if not isinstance(receipt_outcome, dict):
                continue
            outcome = receipt_outcome.get("outcome")
            if not isinstance(outcome, dict):
                continue
            if outcome.get("executor_id") != self.market_contract:
                continue
            if not _successful_status(outcome.get("status")):
                continue
            receipt_id = receipt_outcome.get("id")
            block_hash = receipt_outcome.get("block_hash")
            if not isinstance(receipt_id, str) or not isinstance(block_hash, str):
                raise PulseIndexError("receipt outcome was missing its identity")
            block_height, canonical_block_hash, timestamp_ns = self._receipt_block(block_hash)
            for log_index, raw_log in enumerate(outcome.get("logs", [])):
                if not isinstance(raw_log, str) or not raw_log.startswith(EVENT_PREFIX):
                    continue
                try:
                    event = json.loads(raw_log[len(EVENT_PREFIX) :])
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("standard") != "notch-market" or event.get("event") != "position_entered":
                    continue
                for data in _event_data_items(event.get("data")):
                    market_id = data.get("market_id")
                    account_id = data.get("account_id")
                    sender_id = data.get("sender_id")
                    predecessor = data.get("predecessor")
                    amount = _canonical_amount(data.get("amount"))
                    event_outcome = data.get("outcome")
                    if not isinstance(market_id, str) or not market_id:
                        continue
                    if not isinstance(account_id, str) or not account_id:
                        continue
                    if sender_id != account_id or predecessor != self.collateral_token:
                        continue
                    if isinstance(event_outcome, bool) or not isinstance(event_outcome, int) or event_outcome < 0:
                        continue
                    if amount is None:
                        continue
                    if not any(
                        candidate["market_id"] == market_id
                        and candidate["outcome"] == event_outcome
                        and candidate["amount"] == amount
                        for candidate in candidates
                    ):
                        continue
                    events.append(
                        PulseEvent(
                            event_id=f"{tx_hash}:{receipt_id}:{log_index}",
                            tx_hash=tx_hash,
                            receipt_id=receipt_id,
                            log_index=log_index,
                            block_height=block_height,
                            block_hash=canonical_block_hash,
                            block_timestamp_ns=timestamp_ns,
                            market_id=market_id,
                            account_id=account_id,
                            outcome=event_outcome,
                            amount_base_units=amount,
                        )
                    )
        return events

    def _scan_block(self, block: dict[str, Any]) -> tuple[int, str, int, list[PulseEvent]]:
        height, block_hash, timestamp_ns = self._header(block)
        events: list[PulseEvent] = []
        for chunk_info in block.get("chunks", []):
            if not isinstance(chunk_info, dict):
                continue
            chunk_hash = chunk_info.get("chunk_hash")
            if not isinstance(chunk_hash, str) or not chunk_hash:
                continue
            chunk = self._rpc("chunk", {"chunk_id": chunk_hash})
            if not isinstance(chunk, dict):
                raise PulseIndexError("final RPC returned an invalid chunk")
            for transaction in chunk.get("transactions", []):
                candidates = self._entry_candidates(transaction)
                if candidates:
                    events.extend(self._events_for_transaction(transaction, candidates))
        return height, block_hash, timestamp_ns, events

    def sync(self, *, max_blocks: int | None = None) -> PulseSyncResult:
        with self._lock:
            limit = max(1, min(max_blocks or self.max_blocks, 500))
            try:
                latest = self._rpc("block", {"finality": "final"})
                latest_height, _latest_hash, latest_timestamp_ns = self._header(latest)
                self.store.set_latest_final(height=latest_height, timestamp_ns=latest_timestamp_ns)
                cursor = self.store.cursor_height()
                if cursor is None:
                    if self.start_block is None:
                        # Establish the boundary without pretending to backfill history.
                        self.store.initialize_tracking(
                            start_height=latest_height,
                            start_timestamp_ns=latest_timestamp_ns,
                            cursor_height=latest_height,
                            cursor_hash=_latest_hash,
                            cursor_timestamp_ns=latest_timestamp_ns,
                        )
                        self.store.clear_error()
                        return PulseSyncResult(
                            initialized=True,
                            scanned_blocks=0,
                            from_height=None,
                            to_height=None,
                            latest_final_height=latest_height,
                            events_found=0,
                        )
                    start = int(self.start_block)
                    if start < 0 or start > latest_height:
                        raise PulseIndexError("configured Pulse start block is outside finalized chain")
                    start_block = self._rpc("block", {"block_id": start})
                    start_height, start_hash, start_timestamp_ns = self._header(start_block)
                    if start_height != start:
                        raise PulseIndexError("configured Pulse start block did not resolve to the requested height")
                    self.store.initialize_tracking(
                        start_height=start,
                        start_timestamp_ns=start_timestamp_ns,
                        cursor_height=start - 1,
                        cursor_hash=None,
                        cursor_timestamp_ns=None,
                    )
                    cursor = start - 1
                if cursor >= latest_height:
                    self.store.clear_error()
                    return PulseSyncResult(
                        initialized=False,
                        scanned_blocks=0,
                        from_height=None,
                        to_height=None,
                        latest_final_height=latest_height,
                        events_found=0,
                    )
                first = cursor + 1
                target = min(latest_height, cursor + limit)
                event_count = 0
                for height in range(first, target + 1):
                    block = self._rpc("block", {"block_id": height})
                    actual_height, block_hash, timestamp_ns, events = self._scan_block(block)
                    if actual_height != height:
                        raise PulseIndexError("block height changed while scanning finalized history")
                    event_count += self.store.commit_block(
                        height=actual_height,
                        block_hash=block_hash,
                        timestamp_ns=timestamp_ns,
                        events=events,
                    )
                self.store.clear_error()
                return PulseSyncResult(
                    initialized=False,
                    scanned_blocks=target - first + 1,
                    from_height=first,
                    to_height=target,
                    latest_final_height=latest_height,
                    events_found=event_count,
                )
            except (NearRpcError, PulseIndexError, KeyError, TypeError, ValueError) as exc:
                message = str(exc) or type(exc).__name__
                self.store.record_sync_error(message)
                return PulseSyncResult(
                    initialized=False,
                    scanned_blocks=0,
                    from_height=None,
                    to_height=None,
                    latest_final_height=None,
                    events_found=0,
                    error=message,
                )

    def payload(
        self,
        *,
        window: str = "7d",
        refresh: bool = True,
        max_blocks: int | None = None,
    ) -> dict[str, Any]:
        if window not in WINDOW_SECONDS:
            raise ValueError(f"unsupported Pulse window: {window}")
        sync = self.sync(max_blocks=max_blocks) if refresh else PulseSyncResult(
            initialized=False,
            scanned_blocks=0,
            from_height=None,
            to_height=None,
            latest_final_height=None,
            events_found=0,
        )
        data = self.store.summary(window=window)
        return {
            "data": data,
            "meta": {
                "network": "testnet",
                "indexer": "local_final_rpc_cursor",
                "refresh_requested": refresh,
                "sync": sync.to_dict(),
            },
        }


def empty_pulse_payload(*, window: str = "7d", reason: str = "not_configured") -> dict[str, Any]:
    """Return an explicit no-data state when the API has no indexer configured."""
    return {
        "data": {
            "coverage": {
                "available": False,
                "status": reason,
                "source": "NEAR finalized RPC receipts",
                "scope": "accepted position_entered events observed after tracking began",
                "historical_backfill": False,
                "started_at_utc": None,
                "start_block_height": None,
                "last_scanned_block_height": None,
                "last_scanned_at_utc": None,
                "latest_final_block_height": None,
                "latest_final_at_utc": None,
                "indexed_event_count": 0,
                "last_error": None,
                "limitations": ["Pulse indexing is not configured for this API process."],
            },
            "as_of_utc": None,
            "window": window,
            "currency": {"symbol": "USDC", "decimals": 6, "unit": "base_units"},
            "metrics": {
                "forecaster_count": 0,
                "new_forecaster_count": 0,
                "confirmed_volume_base_units": "0",
                "successful_entries": 0,
                "successful_entry_events": 0,
            },
            "hot_markets": [],
            "recent_calls": [],
        },
        "meta": {"network": "testnet", "indexer": "not_configured"},
    }
