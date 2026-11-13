"""Read-only repositories over existing Radar and Oracle stores."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from services.oracle.evidence import verify_evidence
from services.oracle.store import OracleStore
from services.trend_radar.canonical import normalize_name
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

    def list_scout_candidates(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not Path(self.path).exists():
            raise RepositoryError(f"Radar database not found: {self.path}")
        store = RadarStore(self.path)
        try:
            return store.list_candidates(limit=max(1, min(int(limit), 100)))
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


def _topic_names(rule: dict[str, Any]) -> set[str]:
    names = {
        str(item.get("article_title"))
        for item in rule.get("topics", [])
        if item.get("article_title")
    }
    article = (rule.get("source") or {}).get("article")
    if article:
        names.add(str(article))
    return names


def _source_signature(rule: dict[str, Any]) -> tuple[Any, ...]:
    source = rule.get("source") or {}
    return tuple(source.get(key) for key in ("id", "project", "metric", "granularity", "access", "agent", "timezone"))


def _formula_signature(rule: dict[str, Any]) -> tuple[Any, ...]:
    formula = rule.get("formula") or {}
    return tuple(formula.get(key) for key in ("version", "growth_bps", "threshold_bps", "up_if", "down_if", "integer_only", "rounding"))


def _observation_span(rule: dict[str, Any]) -> int | None:
    observation = rule.get("observation") or {}
    try:
        return (date.fromisoformat(str(observation["target_date"])) - date.fromisoformat(str(observation["baseline_date"]))).days
    except (KeyError, TypeError, ValueError):
        return None


def _replay_methodology_matches(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if str(candidate.get("mode")) != str(current.get("mode")):
        return False
    if not _topic_names(current).intersection(_topic_names(candidate)):
        return False
    if _source_signature(current) != _source_signature(candidate):
        return False
    if _formula_signature(current) != _formula_signature(candidate):
        return False
    if _observation_span(current) != _observation_span(candidate):
        return False
    if (candidate.get("minimum_baseline_views") is not None
            and candidate.get("minimum_baseline_views") != current.get("minimum_baseline_views")):
        return False
    for key in ("missing_data_policy", "invalidation_policy"):
        if candidate.get(key) != current.get(key):
            return False
    return True


def _calibration_methodology_matches(rule: dict[str, Any], calibration: dict[str, Any], article: str | None) -> bool:
    if str(calibration.get("mode")) != str(rule.get("mode")) or str(calibration.get("article")) != str(article):
        return False
    source = rule.get("source") or {}
    if calibration.get("project") and source.get("project") and calibration.get("project") != source.get("project"):
        return False
    if calibration.get("min_baseline_views") is not None and calibration.get("min_baseline_views") != rule.get("minimum_baseline_views"):
        return False
    if rule.get("mode") == "trend_trading":
        policy = str(calibration.get("threshold_policy") or "")
        return "7-day growth" in policy and "threshold" in policy
    if rule.get("mode") == "trend_battle":
        policy = str(calibration.get("tie_policy") or "")
        return "absolute 7-day growth" in policy
    return False


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

    def matching_historical_context(self, rule_record: dict[str, Any], *, limit: int = 4) -> list[dict[str, Any]]:
        """Return only same-topic, same-method historical oracle context."""
        rule = rule_record.get("rule", rule_record)
        market_id = str(rule.get("market_id") or rule_record.get("market_id") or "")
        mode = str(rule.get("mode") or rule_record.get("mode") or "")
        matches: list[dict[str, Any]] = []
        seen: set[str] = set()
        for store in self._stores():
            try:
                for row in store.list_calibrations():
                    calibration = row.get("calibration") or {}
                    article = str(row.get("article") or calibration.get("article") or "")
                    calibration_for_match = {**calibration, "mode": row.get("mode") or calibration.get("mode"), "article": article}
                    if not _calibration_methodology_matches(rule, calibration_for_match, article):
                        continue
                    digest = str(row.get("report_digest") or calibration.get("report_digest") or "")
                    if not digest or digest in seen:
                        continue
                    seen.add(digest)
                    matches.append({
                        "kind": "calibration",
                        "source_id": f"oracle:calibration:{digest}",
                        "report_digest": digest,
                        "article": row.get("article") or calibration.get("article"),
                        "mode": row.get("mode") or calibration.get("mode"),
                        "calibration": calibration,
                    })
                for row in store.list_rules(status="APPROVED"):
                    candidate = row.get("rule") or {}
                    if str(row.get("market_id")) == market_id or str(candidate.get("mode")) != mode:
                        continue
                    if not (candidate.get("observation") or {}).get("replay"):
                        continue
                    if not _replay_methodology_matches(rule, candidate):
                        continue
                    evidence_rows = store.list_evidence(market_id=str(row.get("market_id")))
                    if not evidence_rows:
                        continue
                    evidence = evidence_rows[0]["evidence"]
                    verification = verify_evidence(evidence, expected_rule_hash=str(row.get("rule_hash") or ""))
                    if not verification.get("valid"):
                        continue
                    digest = str(evidence.get("evidence_digest") or "")
                    if not digest or digest in seen:
                        continue
                    seen.add(digest)
                    matches.append({
                        "kind": "historical_replay",
                        "source_id": f"oracle:replay:{digest}",
                        "market_id": row.get("market_id"),
                        "rule": candidate,
                        "evidence": evidence,
                    })
            finally:
                store.close()
        return matches[:limit]

    def published_topic_matches(self, market_ids: set[str]) -> dict[str, dict[str, Any]]:
        matches: dict[str, dict[str, Any]] = {}
        seen: set[tuple[str, str]] = set()
        for store in self._stores():
            try:
                for status in ("APPROVED", "PUBLISHED"):
                    for row in store.list_rules(status=status):
                        market_id = str(row.get("market_id") or "")
                        if not market_id or market_id not in market_ids:
                            continue
                        rule = row.get("rule") or {}
                        names = sorted(_topic_names(rule))
                        match = {
                            "market_id": market_id,
                            "status": row.get("status"),
                            "rule_hash": row.get("rule_hash"),
                            "question": rule.get("question"),
                            "topics": names,
                        }
                        for name in names:
                            key = normalize_name(name)
                            marker = (key, market_id)
                            if key and marker not in seen:
                                seen.add(marker)
                                matches[key] = match
            finally:
                store.close()
        return matches

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
