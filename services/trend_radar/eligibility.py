"""Market eligibility evaluation, independent of discovery ranking."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .models import (
    Candidate,
    EligibilityStatus,
    SettlementCoverage,
    SourceHealth,
)

STALE_AFTER_DAYS = 7


def measurement_signature(candidate: Candidate) -> dict[str, str] | None:
    if not candidate.discovery_signals.get("settlement_article"):
        return None
    configured = candidate.discovery_signals.get("measurement_signature")
    if isinstance(configured, dict):
        return configured
    return {
        "source": "wikimedia-pageviews-v1",
        "project": "en.wikipedia.org",
        "access": "all-access",
        "agent": "user",
        "metric": "daily_pageviews",
    }


def battle_compatible(a: Candidate, b: Candidate) -> bool:
    if a.eligibility_status != EligibilityStatus.ELIGIBLE:
        return False
    if b.eligibility_status != EligibilityStatus.ELIGIBLE:
        return False
    if a.candidate_id == b.candidate_id:
        return False
    article_a = a.discovery_signals.get("settlement_article")
    article_b = b.discovery_signals.get("settlement_article")
    if not article_a or not article_b or article_a == article_b:
        return False
    return measurement_signature(a) == measurement_signature(b)


def evaluate_candidates(
    candidates: Iterable[Candidate],
    *,
    health_by_source: dict[str, SourceHealth],
    coverage_by_candidate: dict[str, SettlementCoverage],
    probed_ids: set[str],
    now: datetime,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> list[Candidate]:
    for candidate in candidates:
        reasons: list[str] = []
        candidate.eligibility_reasons = reasons
        candidate.proposed_market_modes = []
        sources = candidate.discovery_signals.get("sources") or []
        health = [health_by_source.get(source) for source in sources]
        all_stale = bool(health) and all(
            item is None or item.stale or item.status.value in {"failed", "skipped"}
            for item in health
        )
        stale_observation = now - candidate.observed_at > timedelta(days=stale_after_days)
        article = candidate.discovery_signals.get("settlement_article")
        coverage = coverage_by_candidate.get(candidate.candidate_id)

        if not candidate.title.strip() or not candidate.source_identities:
            candidate.eligibility_status = EligibilityStatus.REJECTED
            reasons.append("invalid_source_record")
            continue
        if stale_observation or all_stale:
            candidate.eligibility_status = EligibilityStatus.STALE
            reasons.append("stale_observation" if stale_observation else "stale_source")
            continue
        if candidate.discovery_signals.get("ambiguous"):
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("ambiguous_topic")
            continue
        if not article:
            candidate.eligibility_status = EligibilityStatus.NOT_MEASURABLE
            reasons.append("no_settlement_coverage")
            continue
        if candidate.candidate_id not in probed_ids:
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("coverage_probe_not_run")
            continue
        if coverage is None:
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("coverage_probe_missing")
            continue

        candidate.settlement_coverage = coverage
        if coverage.status == "not_found":
            candidate.eligibility_status = EligibilityStatus.NOT_MEASURABLE
            reasons.append("wikimedia_pageviews_not_found")
            continue
        if coverage.status == "error":
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("coverage_probe_failed")
            continue
        if coverage.status == "incomplete":
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("incomplete_history")
            continue
        if coverage.status == "insufficient_baseline":
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("baseline_below_minimum")
            continue
        if coverage.measurable:
            candidate.eligibility_status = EligibilityStatus.ELIGIBLE
            reasons.append("eligible_settlement_coverage")
            candidate.proposed_market_modes = ["trend_trading"]
            candidate.notes.append(
                "Eligible for PROPOSED market drafts only; the rule and evidence "
                "must be frozen by S3B before any onchain creation."
            )
        else:
            candidate.eligibility_status = EligibilityStatus.NEEDS_REVIEW
            reasons.append("coverage_not_measurable")
    return list(candidates)
