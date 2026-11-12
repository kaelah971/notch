"""Durable local storage for radar scans, source snapshots and decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    Decision,
    ProposalStatus,
    iso_utc,
    jsonable,
    parse_iso,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    result_json TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_scan_runs_fingerprint
    ON scan_runs(fingerprint, status, started_at);

CREATE TABLE IF NOT EXISTS source_snapshots (
    source TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    reporting_date TEXT,
    stale INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    attempted_at TEXT,
    last_success_at TEXT,
    error TEXT,
    stale INTEGER NOT NULL DEFAULT 0,
    cache_used INTEGER NOT NULL DEFAULT 0,
    item_count INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    rate_limited INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    canonical_topic_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    eligibility_status TEXT NOT NULL,
    score INTEGER NOT NULL,
    candidate_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_rank
    ON candidates(score DESC, candidate_id ASC);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    candidate_ids_json TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decision_reason TEXT,
    decided_by TEXT,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposals_status
    ON proposals(status, proposal_id);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class RadarStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Scan runs
    # ------------------------------------------------------------------
    def expire_stale_scans(self, now: datetime, timeout_seconds: int = 900) -> None:
        cutoff = iso_utc(now - timedelta(seconds=timeout_seconds))
        with self.conn:
            self.conn.execute(
                "UPDATE scan_runs SET status='failed', error='stale running scan', "
                "completed_at=? WHERE status='running' AND started_at < ?",
                (iso_utc(now), cutoff),
            )

    def running_scan(self, now: datetime, timeout_seconds: int = 900) -> dict[str, Any] | None:
        self.expire_stale_scans(now, timeout_seconds)
        cutoff = iso_utc(now - timedelta(seconds=timeout_seconds))
        row = self.conn.execute(
            "SELECT * FROM scan_runs WHERE status='running' AND started_at >= ? "
            "ORDER BY started_at DESC LIMIT 1",
            (cutoff,),
        ).fetchone()
        return dict(row) if row else None

    def recent_completed_scan(
        self, fingerprint: str, since: datetime
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM scan_runs WHERE fingerprint=? AND status='completed' "
            "AND started_at >= ? ORDER BY started_at DESC LIMIT 1",
            (fingerprint, iso_utc(since)),
        ).fetchone()
        return dict(row) if row else None

    def start_scan(
        self,
        scan_id: str,
        fingerprint: str,
        sources: list[str],
        started_at: datetime,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO scan_runs(scan_id, fingerprint, sources_json, status, started_at) "
                "VALUES (?, ?, ?, 'running', ?)",
                (
                    scan_id,
                    fingerprint,
                    json.dumps(sources, ensure_ascii=False),
                    iso_utc(started_at),
                ),
            )

    def complete_scan(
        self, scan_id: str, result: Any, completed_at: datetime
    ) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE scan_runs SET status='completed', completed_at=?, result_json=? "
                "WHERE scan_id=?",
                (
                    iso_utc(completed_at),
                    json.dumps(jsonable(result), ensure_ascii=False),
                    scan_id,
                ),
            )

    def fail_scan(self, scan_id: str, error: str, completed_at: datetime) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE scan_runs SET status='failed', completed_at=?, error=? "
                "WHERE scan_id=?",
                (iso_utc(completed_at), error, scan_id),
            )

    # ------------------------------------------------------------------
    # Source snapshots and health
    # ------------------------------------------------------------------
    def save_source_snapshot(
        self,
        source: str,
        payload: Any,
        fetched_at: datetime,
        payload_hash: str,
        reporting_date: str | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO source_snapshots(source, fetched_at, payload_hash, payload_json, reporting_date) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET fetched_at=excluded.fetched_at, "
                "payload_hash=excluded.payload_hash, payload_json=excluded.payload_json, "
                "reporting_date=excluded.reporting_date, stale=0",
                (
                    source,
                    iso_utc(fetched_at),
                    payload_hash,
                    json.dumps(payload, ensure_ascii=False),
                    reporting_date,
                ),
            )

    def get_source_snapshot(self, source: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM source_snapshots WHERE source=?", (source,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def save_source_health(self, health: Any) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO source_health(source, status, attempted_at, last_success_at, error, "
                "stale, cache_used, item_count, latency_ms, rate_limited, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET status=excluded.status, "
                "attempted_at=excluded.attempted_at, "
                "last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at), "
                "error=excluded.error, stale=excluded.stale, cache_used=excluded.cache_used, "
                "item_count=excluded.item_count, latency_ms=excluded.latency_ms, "
                "rate_limited=excluded.rate_limited, detail=excluded.detail",
                (
                    health.source,
                    health.status.value,
                    iso_utc(health.attempted_at),
                    iso_utc(health.last_success_at),
                    health.error,
                    int(health.stale),
                    int(health.cache_used),
                    health.item_count,
                    health.latency_ms,
                    int(health.rate_limited),
                    health.detail,
                ),
            )

    def source_health(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM source_health ORDER BY source"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["stale"] = bool(item["stale"])
            item["cache_used"] = bool(item["cache_used"])
            item["rate_limited"] = bool(item["rate_limited"])
            result.append(item)
        return result

    def last_successful_update(self) -> datetime | None:
        row = self.conn.execute(
            "SELECT MAX(last_success_at) AS value FROM source_health"
        ).fetchone()
        return parse_iso(row["value"]) if row and row["value"] else None

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------
    def upsert_candidate(self, candidate: Any) -> None:
        payload = json.dumps(jsonable(candidate), ensure_ascii=False)
        with self.conn:
            self.conn.execute(
                "INSERT INTO candidates(candidate_id, canonical_topic_id, title, category, "
                "eligibility_status, score, candidate_json, first_seen_at, last_seen_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(candidate_id) DO UPDATE SET canonical_topic_id=excluded.canonical_topic_id, "
                "title=excluded.title, category=excluded.category, "
                "eligibility_status=excluded.eligibility_status, score=excluded.score, "
                "candidate_json=excluded.candidate_json, last_seen_at=excluded.last_seen_at, "
                "updated_at=excluded.updated_at",
                (
                    candidate.candidate_id,
                    candidate.canonical_topic_id,
                    candidate.title,
                    candidate.category.value,
                    candidate.eligibility_status.value,
                    int(candidate.discovery_signals.get("score", 0)),
                    payload,
                    iso_utc(candidate.first_seen_at),
                    iso_utc(candidate.last_seen_at),
                    iso_utc(candidate.last_seen_at),
                ),
            )

    def previous_first_seen(self) -> dict[str, datetime]:
        rows = self.conn.execute(
            "SELECT canonical_topic_id, first_seen_at FROM candidates"
        ).fetchall()
        result = {}
        for row in rows:
            parsed = parse_iso(row["first_seen_at"])
            if parsed:
                result[row["canonical_topic_id"]] = parsed
        return result

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT candidate_json FROM candidates WHERE candidate_id=?",
            (candidate_id,),
        ).fetchone()
        return json.loads(row["candidate_json"]) if row else None

    def list_candidates(
        self,
        *,
        category: str | None = None,
        eligibility: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if category:
            clauses.append("category=?")
            params.append(category)
        if eligibility:
            clauses.append("eligibility_status=?")
            params.append(eligibility)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT candidate_json FROM candidates {where} "
            "ORDER BY score DESC, candidate_id ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [json.loads(row["candidate_json"]) for row in rows]

    # ------------------------------------------------------------------
    # Proposals and operator decisions
    # ------------------------------------------------------------------
    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["proposal"] = json.loads(item.pop("proposal_json"))
        item["candidate_ids"] = json.loads(item.pop("candidate_ids_json"))
        return item

    def list_proposals(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM proposals WHERE status=? ORDER BY proposal_id ASC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM proposals ORDER BY proposal_id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["proposal"] = json.loads(item.pop("proposal_json"))
            item["candidate_ids"] = json.loads(item.pop("candidate_ids_json"))
            result.append(item)
        return result

    def apply_existing_decision(self, proposal: Any) -> Any:
        existing = self.get_proposal(proposal.proposal_id)
        if existing:
            proposal.status = ProposalStatus(existing["status"])
            proposal.decision_reason = existing.get("decision_reason")
            proposal.decided_by = existing.get("decided_by")
            proposal.decided_at = parse_iso(existing.get("decided_at"))
        return proposal

    def upsert_proposal(self, proposal: Any, updated_at: datetime) -> None:
        payload = json.dumps(jsonable(proposal), ensure_ascii=False)
        existing = self.get_proposal(proposal.proposal_id)
        with self.conn:
            if existing:
                self.conn.execute(
                    "UPDATE proposals SET proposal_json=?, updated_at=? WHERE proposal_id=?",
                    (payload, iso_utc(updated_at), proposal.proposal_id),
                )
            else:
                self.conn.execute(
                    "INSERT INTO proposals(proposal_id, candidate_ids_json, mode, status, "
                    "proposal_json, created_at, updated_at, decision_reason, decided_by, decided_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        proposal.proposal_id,
                        json.dumps(proposal.candidate_ids, ensure_ascii=False),
                        proposal.mode.value,
                        proposal.status.value,
                        payload,
                        iso_utc(proposal.created_at),
                        iso_utc(updated_at),
                        proposal.decision_reason,
                        proposal.decided_by,
                        iso_utc(proposal.decided_at),
                    ),
                )

    def review_proposal(
        self,
        proposal_id: str,
        decision: Decision,
        reason: str,
        operator: str,
        now: datetime,
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError("a review reason is required")
        existing = self.get_proposal(proposal_id)
        if not existing:
            raise KeyError(f"unknown proposal: {proposal_id}")
        status = (
            ProposalStatus.APPROVED
            if decision == Decision.APPROVE
            else ProposalStatus.REJECTED
        )
        proposal = existing["proposal"]
        proposal["status"] = status.value
        proposal["decision_reason"] = reason
        proposal["decided_by"] = operator
        proposal["decided_at"] = iso_utc(now)
        with self.conn:
            self.conn.execute(
                "UPDATE proposals SET status=?, proposal_json=?, updated_at=?, "
                "decision_reason=?, decided_by=?, decided_at=? WHERE proposal_id=?",
                (
                    status.value,
                    json.dumps(proposal, ensure_ascii=False),
                    iso_utc(now),
                    reason,
                    operator,
                    iso_utc(now),
                    proposal_id,
                ),
            )
            self.conn.execute(
                "INSERT INTO decisions(target_type, target_id, decision, reason, operator, created_at) "
                "VALUES ('proposal', ?, ?, ?, ?, ?)",
                (proposal_id, status.value, reason, operator, iso_utc(now)),
            )
        updated = self.get_proposal(proposal_id)
        assert updated is not None
        return updated
