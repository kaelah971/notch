"""Shared test helpers for the Trend Radar."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.http import FetchError, FetchResult, FixtureFetcher
from services.trend_radar.models import (
    CANDIDATE_SCHEMA,
    Candidate,
    Category,
    EligibilityStatus,
    SettlementCoverage,
    SourceHealth,
    SourceStatus,
)

FIXED_NOW = datetime(2026, 11, 11, 23, 45, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture_fetcher(now: datetime = FIXED_NOW) -> FixtureFetcher:
    return FixtureFetcher(FIXTURES, now_fn=lambda: now)


class StaticFetcher:
    """Returns provided JSON responses for URL substring matches."""

    def __init__(self, responses: dict[str, Any], fetched_at: datetime = FIXED_NOW):
        self.responses = responses
        self.fetched_at = fetched_at

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        for marker, data in self.responses.items():
            if marker in url:
                if callable(data):
                    result = data(url)
                    if isinstance(result, FetchResult):
                        return result
                    data = result
                text = canonical_json(data)
                return FetchResult(
                    data=data,
                    url=url,
                    source=source,
                    fetched_at=self.fetched_at,
                    raw_hash=sha256_text(text),
                )
        raise FetchError(
            f"no static response for {url}", url=url, kind="not_found", status=404
        )


class FailingFetcher:
    """Fails selected sources and optionally delegates the rest."""

    def __init__(self, failures: set[str], wrapped: Any | None = None):
        self.failures = failures
        self.wrapped = wrapped

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        if source in self.failures:
            raise FetchError(
                f"{source} unavailable in test",
                url=url,
                kind="rate_limit" if source == "coingecko" else "network",
                status=429 if source == "coingecko" else None,
                retryable=True,
            )
        if self.wrapped is None:
            raise FetchError(
                f"{source} unavailable in test", url=url, kind="network"
            )
        return self.wrapped.get_json(url, source=source, **kwargs)


class StaleFetcher:
    """Wraps fixtures and marks every response as stale cache."""

    def __init__(self, wrapped: Any):
        self.wrapped = wrapped

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        result = self.wrapped.get_json(url, source=source, **kwargs)
        return dataclasses.replace(result, from_cache=True, stale=True)


def make_candidate(
    *,
    candidate_id: str = "cand_test",
    canonical_topic_id: str | None = None,
    title: str = "Test Topic",
    category: Category = Category.AI,
    sources: tuple[str, ...] = ("wikimedia",),
    settlement_article: str | None = "Test Topic",
    settlement_page_id: int | None = 1,
    observed_at: datetime = FIXED_NOW,
    evidence: list[dict[str, Any]] | None = None,
    source_identities: list[dict[str, Any]] | None = None,
    ambiguous: bool = False,
    score: int | None = None,
    status: EligibilityStatus = EligibilityStatus.NEEDS_REVIEW,
) -> Candidate:
    canonical = canonical_topic_id or f"test:{candidate_id}"
    if evidence is None:
        evidence = [
            {
                "source": source,
                "source_id": f"{source}:{candidate_id}",
                "title": title,
                "url": f"https://example.test/{source}/{candidate_id}",
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "metrics": {"rank": 20} if source == "wikimedia" else {"points": 200},
                "source_identity": {"source": source},
                "raw_hash": "abc",
            }
            for source in sources
        ]
    if source_identities is None:
        source_identities = [
            {"source": source, "source_id": f"{source}:{candidate_id}", "url": "https://example.test"}
            for source in sources
        ]
    candidate = Candidate(
        schema_version=CANDIDATE_SCHEMA,
        candidate_id=candidate_id,
        canonical_topic_id=canonical,
        title=title,
        category=category,
        aliases=[title],
        source_identities=source_identities,
        discovery_evidence=evidence,
        source_urls=["https://example.test"],
        first_seen_at=observed_at,
        last_seen_at=FIXED_NOW,
        observed_at=observed_at,
        discovery_signals={
            "source_count": len(set(sources)),
            "sources": list(sources),
            "settlement_article": settlement_article,
            "settlement_page_id": settlement_page_id,
            "settlement_source": "observed_wiki_article" if settlement_article else None,
            "ambiguous": ambiguous,
        },
        eligibility_status=status,
        eligibility_reasons=[],
        confidence=0,
        reliability="low",
        proposed_market_modes=[],
    )
    if score is not None:
        candidate.discovery_signals["score"] = score
    return candidate


def make_coverage(
    *,
    status: str = "ok",
    min_views: int | None = 5000,
    days: int = 7,
    article: str = "Test Topic",
    baseline: int = 1000,
    error: str | None = None,
) -> SettlementCoverage:
    daily = [
        {"date": f"2026-11-{4 + index:02d}", "views": min_views or 5000}
        for index in range(days)
    ]
    return SettlementCoverage(
        article=article,
        page_id=1,
        status=status,
        daily_views=daily,
        window_start="2026-11-04",
        window_end="2026-11-10",
        min_views=min_views,
        mean_views=min_views,
        min_baseline_views=baseline,
        error=error,
    )


def make_health(
    source: str,
    *,
    status: SourceStatus = SourceStatus.OK,
    stale: bool = False,
) -> SourceHealth:
    return SourceHealth(
        source=source,
        status=status,
        attempted_at=FIXED_NOW,
        last_success_at=FIXED_NOW,
        stale=stale,
        item_count=1,
    )
