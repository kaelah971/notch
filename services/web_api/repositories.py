"""Read-only repositories over existing Radar and Oracle stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.oracle.evidence import verify_evidence
from services.oracle.store import OracleStore
from services.trend_radar.models import iso_utc, now_utc, parse_iso
from services.trend_radar.store import RadarStore


class RepositoryError(RuntimeError):
    pass


class RadarRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def list_candidates(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not Path(self.path).exists():
            raise RepositoryError(f"Radar database not found: {self.path}")
        store = RadarStore(self.path)
        try:
            return store.list_candidates(eligibility="ELIGIBLE", limit=limit)
        finally:
            store.close()

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        if not Path(self.path).exists():
            raise RepositoryError(f"Radar database not found: {self.path}")
        store = RadarStore(self.path)
        try:
            return store.get_candidate(candidate_id)
        finally:
            store.close()

    def summary(self, candidate: dict[str, Any], *, now=None) -> dict[str, Any]:
        now = now or now_utc()
        signals = candidate.get("discovery_signals") or {}
        coverage = candidate.get("settlement_coverage") or {}
        daily = coverage.get("daily_views") or []
        observed = parse_iso(candidate.get("observed_at"))
        age_hours = (
            round(max(0.0, (now - observed).total_seconds() / 3600.0), 2)
            if observed
            else None
        )
        return {
            "candidate_id": candidate.get("candidate_id"),
            "canonical_topic_id": candidate.get("canonical_topic_id"),
            "title": candidate.get("title"),
            "category": candidate.get("category"),
            "eligibility_status": candidate.get("eligibility_status"),
            "score": signals.get("score"),
            "confidence": candidate.get("confidence"),
            "reliability": candidate.get("reliability"),
            "observed_at": candidate.get("observed_at"),
            "freshness": {
                "age_hours": age_hours,
                "first_seen_at": candidate.get("first_seen_at"),
                "last_seen_at": candidate.get("last_seen_at"),
            },
            "source_count": signals.get("source_count"),
            "sources": signals.get("sources") or [],
            "source_urls": candidate.get("source_urls") or [],
            "proposed_market_modes": candidate.get("proposed_market_modes") or [],
            "settlement_coverage": {
                "status": coverage.get("status"),
                "source": coverage.get("source"),
                "article": coverage.get("article"),
                "window_start": coverage.get("window_start"),
                "window_end": coverage.get("window_end"),
                "min_views": coverage.get("min_views"),
                "mean_views": coverage.get("mean_views"),
                "latest_views": daily[-1].get("views") if daily else None,
                "latest_date": daily[-1].get("date") if daily else None,
            }
            if coverage
            else None,
            "notes": candidate.get("notes") or [],
        }

    def detail(self, candidate: dict[str, Any], *, now=None) -> dict[str, Any]:
        return {
            **self.summary(candidate, now=now),
            "candidate": candidate,
            "evidence": candidate.get("discovery_evidence") or [],
        }


class OracleRepository:
    def __init__(self, paths: tuple[str, ...]) -> None:
        self.paths = tuple(paths)

    def _stores(self) -> list[OracleStore]:
        stores = []
        for path in self.paths:
            if Path(path).exists():
                stores.append(OracleStore(path))
        return stores

    def find(self, market_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        for store in self._stores():
            try:
                rule = store.get_rule_by_market(market_id)
                if rule is None:
                    continue
                evidence_records = store.list_evidence(market_id=market_id)
                evidence = evidence_records[0]["evidence"] if evidence_records else None
                return rule, evidence
            finally:
                store.close()
        return None, None

    def find_rule(self, market_id: str) -> dict[str, Any] | None:
        for store in self._stores():
            try:
                rule = store.get_rule_by_market(market_id)
                if rule is not None:
                    return rule
            finally:
                store.close()
        return None

    def verify(self, market_id: str) -> dict[str, Any] | None:
        rule, evidence = self.find(market_id)
        if rule is None:
            return None
        rule_hash = rule.get("rule_hash") or ""
        verification = (
            verify_evidence(evidence, expected_rule_hash=rule_hash)
            if evidence
            else {"valid": False, "reasons": ["EVIDENCE_NOT_FOUND"], "integrity_note": None}
        )
        return {
            "market_id": market_id,
            "rule": rule.get("rule"),
            "rule_available": True,
            "evidence_available": evidence is not None,
            "rule_record": {
                "rule_hash": rule.get("rule_hash"),
                "market_id": rule.get("market_id"),
                "mode": rule.get("mode"),
                "status": rule.get("status"),
                "created_at": rule.get("created_at"),
                "approved_by": rule.get("approved_by"),
                "approved_at": rule.get("approved_at"),
            },
            "evidence": evidence,
            "evidence_digest": evidence.get("evidence_digest") if evidence else None,
            "verification": verification,
            "verified": bool(verification.get("valid")),
        }
