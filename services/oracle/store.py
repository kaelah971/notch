"""SQLite persistence for frozen rules, evidence, reviews and resolution jobs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from services.trend_radar.models import iso_utc, jsonable

from .contract import ResolutionConflict
from .models import ResolutionPlan, ValidationReport
from .rules import RuleValidationError, rule_digest, validate_rule


class FrozenRuleConflict(RuntimeError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    rule_hash TEXT PRIMARY KEY,
    market_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    rule_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    approval_reason TEXT
);
CREATE TABLE IF NOT EXISTS calibrations (
    report_digest TEXT PRIMARY KEY,
    article TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    calibration_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_digest TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    rule_hash TEXT NOT NULL,
    mode TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_market ON evidence(market_id, created_at);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    candidate_ids_json TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    review_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolution_jobs (
    job_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    rule_hash TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_market ON resolution_jobs(market_id, status);
"""


class OracleStore:
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

    def _row_dict(self, row: sqlite3.Row, json_field: str, key: str) -> dict[str, Any]:
        item = dict(row)
        item[key] = json.loads(item.pop(json_field))
        return item

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def freeze_rule(self, rule: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        errors = validate_rule(rule, now=now)
        if errors:
            raise RuleValidationError(", ".join(errors))
        rule_hash = rule_digest(rule)
        existing = self.get_rule(rule_hash)
        if existing:
            return existing
        by_market = self.get_rule_by_market(rule["market_id"])
        if by_market and by_market["rule_hash"] != rule_hash:
            raise FrozenRuleConflict(
                f"market {rule['market_id']} already has a frozen rule "
                f"{by_market['rule_hash']}; use a new market ID"
            )
        with self.conn:
            self.conn.execute(
                "INSERT INTO rules(rule_hash, market_id, mode, status, rule_json, created_at) "
                "VALUES (?, ?, ?, 'DRAFT', ?, ?)",
                (
                    rule_hash,
                    rule["market_id"],
                    rule["mode"],
                    json.dumps(rule, ensure_ascii=False),
                    iso_utc(now),
                ),
            )
        return self.get_rule(rule_hash)

    def get_rule(self, rule_hash: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM rules WHERE rule_hash=?", (rule_hash,)
        ).fetchone()
        return self._row_dict(row, "rule_json", "rule") if row else None

    def get_rule_by_market(self, market_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM rules WHERE market_id=?", (market_id,)
        ).fetchone()
        return self._row_dict(row, "rule_json", "rule") if row else None

    def list_rules(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM rules WHERE status=? ORDER BY created_at, rule_hash",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM rules ORDER BY created_at, rule_hash"
            ).fetchall()
        return [self._row_dict(row, "rule_json", "rule") for row in rows]

    def approve_rule(
        self, rule_hash: str, *, operator: str, reason: str, now: datetime
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError("approval reason is required")
        existing = self.get_rule(rule_hash)
        if not existing:
            raise KeyError(f"unknown rule: {rule_hash}")
        if existing["status"] == "APPROVED":
            return existing
        if existing["status"] != "DRAFT":
            raise FrozenRuleConflict(
                f"rule {rule_hash} cannot be approved from status {existing['status']}"
            )
        with self.conn:
            self.conn.execute(
                "UPDATE rules SET status='APPROVED', approved_by=?, approved_at=?, "
                "approval_reason=? WHERE rule_hash=?",
                (operator, iso_utc(now), reason, rule_hash),
            )
        return self.get_rule(rule_hash)

    # ------------------------------------------------------------------
    # Calibrations, evidence and reviews
    # ------------------------------------------------------------------
    def save_calibration(self, report: Any, *, now: datetime) -> dict[str, Any]:
        payload = jsonable(report)
        digest = payload.get("report_digest")
        if not digest:
            raise ValueError("calibration report has no report_digest")
        existing = self.get_calibration(digest)
        if existing:
            return existing
        with self.conn:
            self.conn.execute(
                "INSERT INTO calibrations(report_digest, article, mode, status, "
                "calibration_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    digest,
                    payload.get("article"),
                    payload.get("mode"),
                    payload.get("status"),
                    json.dumps(payload, ensure_ascii=False),
                    iso_utc(now),
                ),
            )
        return self.get_calibration(digest)

    def get_calibration(self, digest: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM calibrations WHERE report_digest=?", (digest,)
        ).fetchone()
        return self._row_dict(row, "calibration_json", "calibration") if row else None

    def list_calibrations(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM calibrations ORDER BY created_at, report_digest"
        ).fetchall()
        return [
            self._row_dict(row, "calibration_json", "calibration") for row in rows
        ]

    def save_evidence(self, evidence: Any, *, now: datetime) -> dict[str, Any]:
        payload = jsonable(evidence)
        digest = payload["evidence_digest"]
        existing = self.get_evidence(digest)
        if existing:
            return existing
        with self.conn:
            self.conn.execute(
                "INSERT INTO evidence(evidence_digest, market_id, rule_hash, mode, "
                "outcome, evidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    digest,
                    payload["market_id"],
                    payload["rule_hash"],
                    payload["mode"],
                    payload["outcome"],
                    json.dumps(payload, ensure_ascii=False),
                    iso_utc(now),
                ),
            )
        return self.get_evidence(digest)

    def get_evidence(self, digest: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM evidence WHERE evidence_digest=?", (digest,)
        ).fetchone()
        return self._row_dict(row, "evidence_json", "evidence") if row else None

    def list_evidence(self, market_id: str | None = None) -> list[dict[str, Any]]:
        if market_id:
            rows = self.conn.execute(
                "SELECT * FROM evidence WHERE market_id=? ORDER BY created_at, evidence_digest",
                (market_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM evidence ORDER BY created_at, evidence_digest"
            ).fetchall()
        return [self._row_dict(row, "evidence_json", "evidence") for row in rows]

    def save_review(self, review: ValidationReport, *, now: datetime) -> dict[str, Any]:
        payload = jsonable(review)
        review_id = "review_" + hashlib.sha256(
            (
                ",".join(payload["candidate_ids"])
                + ":"
                + payload["recommendation"]
                + ":"
                + iso_utc(now)
            ).encode("utf-8")
        ).hexdigest()[:20]
        with self.conn:
            self.conn.execute(
                "INSERT INTO reviews(review_id, candidate_ids_json, recommendation, "
                "review_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    review_id,
                    json.dumps(payload["candidate_ids"], ensure_ascii=False),
                    payload["recommendation"],
                    json.dumps(payload, ensure_ascii=False),
                    iso_utc(now),
                ),
            )
        return {"review_id": review_id, "review": payload, "created_at": iso_utc(now)}

    def list_reviews(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM reviews ORDER BY created_at, review_id"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["review"] = json.loads(item.pop("review_json"))
            item["candidate_ids"] = json.loads(item.pop("candidate_ids_json"))
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Resolution jobs
    # ------------------------------------------------------------------
    def prepare_job(self, plan: ResolutionPlan, *, now: datetime) -> dict[str, Any]:
        payload = jsonable(plan)
        existing = self.get_job(payload["job_id"])
        if existing:
            existing["idempotent"] = True
            return existing
        conflicts = self.conn.execute(
            "SELECT job_id, evidence_digest, action FROM resolution_jobs "
            "WHERE market_id=? AND status IN ('PREPARED','ALREADY_FINAL') "
            "AND (evidence_digest<>? OR action<>?)",
            (payload["market_id"], payload["evidence_digest"], payload["action"]),
        ).fetchall()
        if conflicts:
            raise ResolutionConflict(
                "conflicting resolution job exists for market "
                f"{payload['market_id']}: "
                + ", ".join(
                    f"{row['job_id']} ({row['action']}/{row['evidence_digest']})"
                    for row in conflicts
                )
            )
        with self.conn:
            self.conn.execute(
                "INSERT INTO resolution_jobs(job_id, market_id, rule_hash, evidence_digest, "
                "action, status, plan_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["job_id"],
                    payload["market_id"],
                    payload["rule_hash"],
                    payload["evidence_digest"],
                    payload["action"],
                    payload["status"],
                    json.dumps(payload, ensure_ascii=False),
                    iso_utc(now),
                    iso_utc(now),
                ),
            )
        return self.get_job(payload["job_id"])

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM resolution_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        return self._row_dict(row, "plan_json", "plan") if row else None

    def list_jobs(self, *, market_id: str | None = None) -> list[dict[str, Any]]:
        if market_id:
            rows = self.conn.execute(
                "SELECT * FROM resolution_jobs WHERE market_id=? "
                "ORDER BY created_at, job_id",
                (market_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM resolution_jobs ORDER BY created_at, job_id"
            ).fetchall()
        return [self._row_dict(row, "plan_json", "plan") for row in rows]
