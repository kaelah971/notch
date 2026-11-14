"""Observed pool-total snapshots for the participation chart.

Each row is a value the S6 API actually read from the market contract, stamped with the
NEAR block timestamp of that read. Rows are written only when a market's totals change,
plus at most one unchanged heartbeat per hour, so the series is sparse and never
interpolated. History begins when this recorder first runs; it cannot be backfilled.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

HEARTBEAT_NS = 3600 * 10**9


class SnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS pool_snapshots (
                market_id TEXT NOT NULL,
                block_ts_ns TEXT NOT NULL,
                totals TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (market_id, block_ts_ns)
            )"""
        )
        self._db.commit()

    def record(self, market: dict[str, Any], block_ts_ns: int) -> None:
        market_id = str(market.get("market_id") or "")
        totals = [str(x) for x in market.get("totals") or []]
        if not market_id or not totals:
            return
        encoded = json.dumps(totals, separators=(",", ":"))
        status = str(market.get("status") or "")
        with self._lock:
            last = self._db.execute(
                "SELECT block_ts_ns, totals, status FROM pool_snapshots WHERE market_id = ? "
                "ORDER BY CAST(block_ts_ns AS INTEGER) DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            if last and last[1] == encoded and last[2] == status and block_ts_ns - int(last[0]) < HEARTBEAT_NS:
                return
            if last and block_ts_ns <= int(last[0]):
                return
            self._db.execute(
                "INSERT OR IGNORE INTO pool_snapshots VALUES (?, ?, ?, ?)",
                (market_id, str(block_ts_ns), encoded, status),
            )
            self._db.commit()

    def history(self, market_id: str, limit: int = 2000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT block_ts_ns, totals, status FROM pool_snapshots WHERE market_id = ? "
                "ORDER BY CAST(block_ts_ns AS INTEGER) ASC LIMIT ?",
                (market_id, limit),
            ).fetchall()
        return [{"block_ts_ns": r[0], "totals": json.loads(r[1]), "status": r[2]} for r in rows]
