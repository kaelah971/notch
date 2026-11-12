"""SQLite cache for generated S5 trend briefs."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import TrendBrief


SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    brief_key TEXT PRIMARY KEY,
    brief_id TEXT NOT NULL UNIQUE,
    brief_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    candidate_id TEXT,
    market_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    generation_status TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    brief_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_briefs_type_created
    ON briefs(brief_type, created_at);
CREATE INDEX IF NOT EXISTS idx_briefs_market
    ON briefs(market_id, created_at);
CREATE INDEX IF NOT EXISTS idx_briefs_candidate
    ON briefs(candidate_id, created_at);
"""


class BriefStore:
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

    def save(self, brief_key: str, brief: TrendBrief) -> TrendBrief:
        payload = json.dumps(brief.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO briefs(
                    brief_key, brief_id, brief_type, topic, candidate_id, market_id,
                    provider, model, generation_status, input_digest, created_at, brief_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(brief_key) DO UPDATE SET
                    brief_type=excluded.brief_type,
                    topic=excluded.topic,
                    candidate_id=excluded.candidate_id,
                    market_id=excluded.market_id,
                    provider=excluded.provider,
                    model=excluded.model,
                    generation_status=excluded.generation_status,
                    input_digest=excluded.input_digest,
                    created_at=excluded.created_at,
                    brief_json=excluded.brief_json
                """,
                (
                    brief_key,
                    brief.brief_id,
                    brief.brief_type,
                    brief.topic,
                    brief.candidate_id,
                    brief.market_id,
                    brief.provider,
                    brief.model,
                    brief.generation_status,
                    brief.input_digest,
                    brief.generated_at,
                    payload,
                ),
            )
        return brief

    def get(self, brief_key: str) -> TrendBrief | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT brief_json FROM briefs WHERE brief_key=?",
                (brief_key,),
            ).fetchone()
        if not row:
            return None
        return TrendBrief.from_dict(json.loads(row["brief_json"]))

    def get_by_id(self, brief_id: str) -> TrendBrief | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT brief_json FROM briefs WHERE brief_id=?",
                (brief_id,),
            ).fetchone()
        if not row:
            return None
        return TrendBrief.from_dict(json.loads(row["brief_json"]))

    def list_briefs(
        self,
        *,
        brief_type: str | None = None,
        candidate_id: str | None = None,
        market_id: str | None = None,
        limit: int = 50,
    ) -> list[TrendBrief]:
        clauses = []
        params: list[Any] = []
        if brief_type:
            clauses.append("brief_type=?")
            params.append(brief_type)
        if candidate_id:
            clauses.append("candidate_id=?")
            params.append(candidate_id)
        if market_id:
            clauses.append("market_id=?")
            params.append(market_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self.conn.execute(
                f"SELECT brief_json FROM briefs {where} ORDER BY created_at DESC LIMIT ?",
                (*params, max(1, min(int(limit), 200))),
            ).fetchall()
        return [TrendBrief.from_dict(json.loads(row["brief_json"])) for row in rows]

    def count(self) -> int:
        with self._lock:
            return int(self.conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0])
