"""Deterministic, documented discovery ranking.

This is a radar/discovery score, not a universal attention index and not a
financial price or settlement metric.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import Candidate, Category, SourceHealth, SourceStatus

RANKING_VERSION = "radar-score/1"


def _prominence(candidate: Candidate) -> tuple[int, dict[str, int]]:
    wiki_rank: int | None = None
    coin_rank: int | None = None
    hn_points = 0
    for evidence in candidate.discovery_evidence:
        source = evidence.get("source")
        metrics = evidence.get("metrics") or {}
        if source == "wikimedia":
            rank = int(metrics.get("rank") or 9999)
            wiki_rank = rank if wiki_rank is None else min(wiki_rank, rank)
        elif source == "coingecko":
            rank = int(metrics.get("trending_rank") or 9999)
            coin_rank = rank if coin_rank is None else min(coin_rank, rank)
        elif source == "hackernews":
            hn_points = max(hn_points, int(metrics.get("points") or 0))

    detail: dict[str, int] = {}
    scores: list[int] = []
    if wiki_rank is not None:
        if wiki_rank <= 10:
            points = 25
        elif wiki_rank <= 50:
            points = 20
        elif wiki_rank <= 200:
            points = 12
        else:
            points = 5
        detail["wikimedia_rank"] = wiki_rank
        detail["wikimedia_points"] = points
        scores.append(points)
    if coin_rank is not None:
        if coin_rank <= 3:
            points = 25
        elif coin_rank <= 10:
            points = 18
        else:
            points = 10
        detail["coingecko_trending_rank"] = coin_rank
        detail["coingecko_points"] = points
        scores.append(points)
    if hn_points:
        if hn_points >= 500:
            points = 25
        elif hn_points >= 200:
            points = 20
        elif hn_points >= 100:
            points = 12
        else:
            points = 5
        detail["hackernews_points"] = hn_points
        detail["hackernews_points_score"] = points
        scores.append(points)
    return (max(scores) if scores else 0), detail


def score_candidate(
    candidate: Candidate,
    health_by_source: dict[str, SourceHealth],
    now: datetime,
) -> dict[str, int]:
    source_count = int(candidate.discovery_signals.get("source_count", 1))
    confirmations = min(20, max(0, (source_count - 1) * 10))

    prominence, prominence_detail = _prominence(candidate)

    age_hours = max(0.0, (now - candidate.observed_at).total_seconds() / 3600.0)
    if age_hours <= 24:
        recency = 20
    elif age_hours <= 48:
        recency = 12
    elif age_hours <= 72:
        recency = 6
    else:
        recency = 0

    coverage = 0
    if candidate.settlement_coverage is not None and candidate.settlement_coverage.measurable:
        coverage = 25
    elif candidate.discovery_signals.get("settlement_article"):
        coverage = 12

    contributing_sources = candidate.discovery_signals.get("sources") or []
    fresh = bool(contributing_sources)
    for source in contributing_sources:
        health = health_by_source.get(source)
        if (
            health is None
            or health.stale
            or health.status not in {SourceStatus.OK, SourceStatus.CACHED}
        ):
            fresh = False
            break
    freshness = 5 if fresh else 0

    relevance = 5 if candidate.category != Category.OTHER else 0
    score = min(
        100,
        confirmations
        + prominence
        + recency
        + coverage
        + freshness
        + relevance,
    )

    candidate.discovery_signals.update(
        {
            "ranking_version": RANKING_VERSION,
            "score": score,
            "score_components": {
                "confirmations": confirmations,
                "prominence": prominence,
                "recency": recency,
                "settlement_coverage": coverage,
                "freshness": freshness,
                "category_relevance": relevance,
            },
            "prominence_detail": prominence_detail,
            "recency_age_hours": round(age_hours, 2),
            "fresh_sources": fresh,
        }
    )
    if candidate.settlement_coverage is not None and candidate.settlement_coverage.measurable:
        candidate.confidence = min(100, 50 + source_count * 10 + (20 if fresh else 0))
        candidate.reliability = "high" if source_count >= 2 and fresh else "medium"
    elif source_count >= 2:
        candidate.confidence = 45
        candidate.reliability = "medium"
    else:
        candidate.confidence = 20
        candidate.reliability = "low"
    return candidate.discovery_signals["score_components"]


def rank_candidates(
    candidates: Iterable[Candidate],
    health_by_source: dict[str, SourceHealth],
    now: datetime,
) -> list[Candidate]:
    ranked = list(candidates)
    for candidate in ranked:
        score_candidate(candidate, health_by_source, now)
    ranked.sort(key=lambda item: (-int(item.discovery_signals.get("score", 0)), item.candidate_id))
    return ranked
