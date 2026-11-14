"""SQLite persistence for bounded Research Council records.

Only structured role output and safe audit metadata are stored. Prompts, raw
provider responses, API keys, and private reasoning are intentionally absent.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS councils (
    council_key TEXT PRIMARY KEY,
    council_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    snapshot_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    council_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_councils_market_created
    ON councils(market_id, created_at);
"""


class ResearchCouncilStore:
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

    def save(self, council_key: str, council: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(council, ensure_ascii=False, sort_keys=True)
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO councils(
                    council_key, council_id, market_id, snapshot_digest, created_at, council_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(council_key) DO UPDATE SET
                    council_id=excluded.council_id,
                    market_id=excluded.market_id,
                    snapshot_digest=excluded.snapshot_digest,
                    created_at=excluded.created_at,
                    council_json=excluded.council_json
                """,
                (
                    council_key,
                    str(council.get("council_id") or ""),
                    str(council.get("market_id") or ""),
                    str(council.get("snapshot", {}).get("snapshot_digest") or ""),
                    str(council.get("created_at") or ""),
                    payload,
                ),
            )
        return council

    def get(self, council_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT council_json FROM councils WHERE council_key=?",
                (council_key,),
            ).fetchone()
        return json.loads(row["council_json"]) if row else None

    def get_by_id(self, council_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT council_json FROM councils WHERE council_id=?",
                (council_id,),
            ).fetchone()
        return json.loads(row["council_json"]) if row else None

    def latest_for_market(self, market_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT council_json FROM councils
                WHERE market_id=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        return json.loads(row["council_json"]) if row else None

    def count(self) -> int:
        with self._lock:
            return int(self.conn.execute("SELECT COUNT(*) FROM councils").fetchone()[0])
