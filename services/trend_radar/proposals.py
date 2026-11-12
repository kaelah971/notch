"""PROPOSED market drafts for operator review. Never onchain creation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Iterable

from .canonical import stable_id
from .eligibility import battle_compatible
from .models import (
    Candidate,
    EligibilityStatus,
    MarketMode,
    MarketProposal,
    PROPOSAL_SCHEMA,
    ProposalStatus,
)

PROPOSAL_VERSION = "s3a-proposal/1"
DEFAULT_THRESHOLD_BPS = 1500
DEFAULT_TIE_TOLERANCE_BPS = 50
MAX_BATTLE_CANDIDATES = 6


def _observation_window(scan_date: date) -> dict[str, str]:
    baseline = scan_date + timedelta(days=3)
    target = baseline + timedelta(days=7)
    resolve_after = target + timedelta(days=2)
    return {
        "baseline_date": baseline.isoformat(),
        "target_date": target.isoformat(),
        "baseline_window_utc": f"{baseline.isoformat()}T00:00:00Z/{baseline.isoformat()}T23:59:59Z",
        "target_window_utc": f"{target.isoformat()}T00:00:00Z/{target.isoformat()}T23:59:59Z",
        "resolve_after_utc": f"{resolve_after.isoformat()}T12:00:00Z",
        "status": "PROPOSED_SUGGESTION",
    }


def _trend_source(article: str) -> dict[str, str]:
    return {
        "id": "wikimedia-pageviews-v1",
        "project": "en.wikipedia.org",
        "article": article,
        "access": "all-access",
        "agent": "user",
        "metric": "daily_pageviews",
        "granularity": "daily",
        "timezone": "UTC",
    }


def _limitations() -> list[str]:
    return [
        "Wikimedia daily pageviews are historical data and can lag publication.",
        "Pageviews are a proxy for attention, not proof of organic interest.",
        "Spikes, bots, redirects and article-title changes can affect observations.",
        "The observation window, threshold, rule hash and tie handling are proposals only.",
        "S3B must freeze and independently reproduce the rule and evidence before market creation.",
    ]


def _trend_proposal(
    candidate: Candidate,
    scan_date: date,
    now: datetime,
    threshold_bps: int,
) -> MarketProposal:
    article = str(candidate.discovery_signals["settlement_article"])
    window = _observation_window(scan_date)
    proposal_id = stable_id(
        "prop",
        f"{PROPOSAL_VERSION}:{candidate.candidate_id}:{MarketMode.TREND_TRADING.value}:"
        f"{window['baseline_date']}:{window['target_date']}",
    )
    question = (
        f"PROPOSED: Will daily en.wikipedia.org pageviews for {article} grow by "
        f"at least {threshold_bps / 100:.2f}% on the full UTC day {window['target_date']} "
        f"versus the full UTC day {window['baseline_date']}? "
        "(Wikimedia Pageviews, all-access, user)"
    )
    return MarketProposal(
        schema_version=PROPOSAL_SCHEMA,
        proposal_id=proposal_id,
        candidate_ids=[candidate.candidate_id],
        mode=MarketMode.TREND_TRADING,
        status=ProposalStatus.PROPOSED,
        topic=candidate.title,
        question=question,
        source=_trend_source(article),
        observation_window=window,
        threshold_bps=threshold_bps,
        tie_tolerance_bps=None,
        tie_policy=None,
        formula="growth-threshold-v1",
        measurement_limitations=_limitations(),
        finalization_required=(
            "S3B deterministic rule freeze, canonical evidence digest and "
            "operator-approved onchain configuration."
        ),
        rule_hash=None,
        created_at=now,
        threshold_status="UNVALIDATED_PROPOSAL",
    )


def _battle_proposal(
    a: Candidate,
    b: Candidate,
    scan_date: date,
    now: datetime,
    tie_tolerance_bps: int,
) -> MarketProposal:
    ordered = sorted([a, b], key=lambda item: item.candidate_id)
    left, right = ordered[0], ordered[1]
    article_a = str(a.discovery_signals["settlement_article"])
    article_b = str(b.discovery_signals["settlement_article"])
    window = _observation_window(scan_date)
    proposal_id = stable_id(
        "prop",
        f"{PROPOSAL_VERSION}:{left.candidate_id}:{right.candidate_id}:"
        f"{MarketMode.TREND_BATTLE.value}:{window['baseline_date']}:{window['target_date']}",
    )
    question = (
        f"PROPOSED: Which topic will have higher normalized Wikimedia pageview growth "
        f"from the full UTC day {window['baseline_date']} to the full UTC day "
        f"{window['target_date']}: {a.title} or {b.title}? "
        f"A growth difference within {tie_tolerance_bps} bps is a tie and voids the market."
    )
    source = _trend_source(article_a)
    source["metric"] = "daily_pageviews_growth_comparison"
    return MarketProposal(
        schema_version=PROPOSAL_SCHEMA,
        proposal_id=proposal_id,
        candidate_ids=[left.candidate_id, right.candidate_id],
        mode=MarketMode.TREND_BATTLE,
        status=ProposalStatus.PROPOSED,
        topic=f"{a.title} vs {b.title}",
        question=question,
        source=source,
        observation_window=window,
        threshold_bps=None,
        tie_tolerance_bps=tie_tolerance_bps,
        tie_policy="void",
        formula="growth_comparison_v1",
        measurement_limitations=_limitations()
        + [
            "Both topics must use the same project, access, agent, metric and observation window.",
            "Tie handling is precommitted as VOID; no winner is invented.",
        ],
        finalization_required=(
            "S3B must freeze the shared battle rule, canonical evidence digest and "
            "tie boundary before market creation."
        ),
        rule_hash=None,
        created_at=now,
        topics=[
            {
                "candidate_id": a.candidate_id,
                "title": a.title,
                "article": article_a,
                "url": f"https://en.wikipedia.org/wiki/{article_a.replace(' ', '_')}",
            },
            {
                "candidate_id": b.candidate_id,
                "title": b.title,
                "article": article_b,
                "url": f"https://en.wikipedia.org/wiki/{article_b.replace(' ', '_')}",
            },
        ],
    )


def build_proposals(
    candidates: Iterable[Candidate],
    *,
    scan_date: date,
    now: datetime,
    threshold_bps: int = DEFAULT_THRESHOLD_BPS,
    tie_tolerance_bps: int = DEFAULT_TIE_TOLERANCE_BPS,
    proposal_limit: int = 10,
    battle_limit: int = 5,
) -> list[MarketProposal]:
    ranked = sorted(
        [candidate for candidate in candidates if candidate.eligibility_status == EligibilityStatus.ELIGIBLE],
        key=lambda item: (-int(item.discovery_signals.get("score", 0)), item.candidate_id),
    )
    proposals: list[MarketProposal] = []
    for candidate in ranked[:proposal_limit]:
        proposals.append(_trend_proposal(candidate, scan_date, now, threshold_bps))

    battle_candidates = ranked[:MAX_BATTLE_CANDIDATES]
    pairs = [
        (a, b)
        for a, b in combinations(battle_candidates, 2)
        if battle_compatible(a, b)
    ]
    pairs.sort(
        key=lambda pair: (
            -(int(pair[0].discovery_signals.get("score", 0))
              + int(pair[1].discovery_signals.get("score", 0))),
            pair[0].candidate_id,
            pair[1].candidate_id,
        )
    )
    for a, b in pairs[:battle_limit]:
        proposals.append(
            _battle_proposal(a, b, scan_date, now, tie_tolerance_bps)
        )
        for candidate in (a, b):
            if MarketMode.TREND_BATTLE.value not in candidate.proposed_market_modes:
                candidate.proposed_market_modes.append(
                    MarketMode.TREND_BATTLE.value
                )
        for proposal_candidate in (a, b):
            if MarketMode.TREND_TRADING.value not in proposal_candidate.proposed_market_modes:
                proposal_candidate.proposed_market_modes.insert(
                    0, MarketMode.TREND_TRADING.value
                )
    return proposals
