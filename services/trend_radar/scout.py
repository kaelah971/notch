"""Deterministic Wikimedia attention discovery for Notch Scout V1.

Scout reads completed Trend Radar records. It never treats pageviews as
sentiment, never publishes a market, and never performs a chain action.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import floor
from typing import Any
from urllib.parse import quote

from .canonical import canonical_json, normalize_name, sha256_text
from .models import iso_utc, parse_iso

SCOUT_VERSION = "notch-scout/1"
SCOUT_SOURCE_ID = "wikimedia-pageviews-v1"
SCOUT_PROJECT = "en.wikipedia.org"
SCOUT_ACCESS = "all-access"
SCOUT_AGENT = "user"
MIN_SAMPLE_DAYS = 5
MIN_BASELINE_VIEWS = 1_000
NOTABLE_CHANGE_BPS = 2_000
UNUSUAL_CHANGE_BPS = 4_000
STALE_AFTER_HOURS = 48
DEFAULT_LIMIT = 12
MAX_LIMIT = 24

# Deliberately small and documented. These are the topics with stable Notch
# Wikimedia mappings and fixture/live coverage used by the existing Radar.
SUPPORTED_TOPICS = (
    "Nvidia",
    "Bitcoin",
    "ChatGPT",
    "Artificial intelligence",
)
_SUPPORTED_BY_KEY = {normalize_name(item): item for item in SUPPORTED_TOPICS}


def pageviews_api_url(article: str, start: str, end: str) -> str:
    article_path = quote(article.replace(" ", "_"), safe="()_,'")
    return (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{SCOUT_PROJECT}/{SCOUT_ACCESS}/{SCOUT_AGENT}/{article_path}/daily/{start.replace('-', '')}00/{end.replace('-', '')}00"
    )


def _parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _expected_days(start: date | None, end: date | None) -> list[str]:
    if start is None or end is None or end < start:
        return []
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def _article(candidate: dict[str, Any]) -> str | None:
    coverage = candidate.get("settlement_coverage") or {}
    signals = candidate.get("discovery_signals") or {}
    return str(coverage.get("article") or signals.get("settlement_article") or candidate.get("title") or "") or None


def _source_url(candidate: dict[str, Any], article: str) -> str:
    for url in candidate.get("source_urls") or []:
        if isinstance(url, str) and "/wiki/" in url:
            return url
    return "https://en.wikipedia.org/wiki/" + quote(article.replace(" ", "_"), safe="()_,'")


def _daily_rows(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in coverage.get("daily_views") or []:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "")
        if not day or day in seen:
            continue
        try:
            views = int(item.get("views"))
        except (TypeError, ValueError):
            continue
        if views < 0:
            continue
        seen.add(day)
        rows.append({"date": day, "views": views})
    rows.sort(key=lambda value: (value["date"], value["views"]))
    return rows


def _movement(baseline: int, current: int) -> int | None:
    if baseline <= 0:
        return None
    return floor((current - baseline) * 10_000 / baseline)


def _status(*, rows: list[dict[str, Any]], baseline: int | None, missing: list[str], stale: bool, coverage_status: str) -> str:
    if not rows or coverage_status in {"not_found", "error"}:
        return "UNAVAILABLE"
    if stale:
        return "STALE"
    if baseline is None or baseline <= 0 or len(rows) < MIN_SAMPLE_DAYS or missing:
        return "NEEDS_REVIEW"
    return "REVIEWABLE"


def _proposal(candidate: dict[str, Any], article: str, item: dict[str, Any]) -> dict[str, Any] | None:
    if item["candidate_status"] != "REVIEWABLE" or not item["is_notable"] or item["existing_market_match"]:
        return None
    end = _parse_day(item["observation_window"].get("end"))
    if end is None:
        return None
    start = end + timedelta(days=1)
    target = end + timedelta(days=7)
    direction = "UP" if item["direction"] == "RISING" else "DOWN"
    verb = "grow" if direction == "UP" else "fall"
    proposal_seed = f"{item['candidate_id']}:{item['evidence_digest']}:{start}:{target}:{direction}"
    return {
        "proposal_id": "scout-proposal-" + sha256_text(proposal_seed)[:20],
        "status": "REVIEW_ONLY",
        "published": False,
        "human_review_required": True,
        "candidate_id": item["candidate_id"],
        "topic": article,
        "question": (
            f"Will daily {SCOUT_PROJECT} pageviews for {article} {verb} by at least "
            f"{NOTABLE_CHANGE_BPS} bps between {start.isoformat()} and {target.isoformat()}?"
        ),
        "source": {
            "id": SCOUT_SOURCE_ID,
            "project": SCOUT_PROJECT,
            "access": SCOUT_ACCESS,
            "agent": SCOUT_AGENT,
            "metric": "daily_pageviews",
            "article": article,
            "article_url": item["source_url"],
            "api_url": pageviews_api_url(article, start.isoformat(), target.isoformat()),
        },
        "observation_window": {
            "comparison_start": start.isoformat(),
            "comparison_end": target.isoformat(),
            "utc_full_days": True,
        },
        "direction": direction,
        "threshold_bps": NOTABLE_CHANGE_BPS,
        "formula": "floor((target_views - baseline_views) * 10000 / baseline_views)",
        "missing_data_handling": "No imputation; require both complete UTC days; zero baseline invalidates the comparison.",
        "evidence_digest": item["evidence_digest"],
        "review_note": "This is a draft for human review only. It is not an on-chain market and cannot be traded.",
    }


def build_scout_candidate(
    candidate: dict[str, Any],
    *,
    now: datetime,
    existing_market_match: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    article = _article(candidate)
    if not article or normalize_name(article) not in _SUPPORTED_BY_KEY:
        return None
    article = _SUPPORTED_BY_KEY[normalize_name(article)]
    coverage = candidate.get("settlement_coverage") or {}
    rows = _daily_rows(coverage)
    start = _parse_day(coverage.get("window_start"))
    end = _parse_day(coverage.get("window_end"))
    expected = _expected_days(start, end)
    actual_days = {row["date"] for row in rows}
    missing = [day for day in expected if day not in actual_days]
    baseline = rows[0] if rows else None
    current = rows[-1] if rows else None
    baseline_views = baseline["views"] if baseline else None
    current_views = current["views"] if current else None
    change_bps = (
        _movement(baseline_views, current_views)
        if baseline_views is not None and current_views is not None
        else None
    )
    observed = parse_iso(candidate.get("observed_at"))
    age_hours = round(max(0.0, (now - observed).total_seconds() / 3600.0), 2) if observed else None
    stale = age_hours is None or age_hours > STALE_AFTER_HOURS
    status = _status(
        rows=rows,
        baseline=baseline_views,
        missing=missing,
        stale=stale,
        coverage_status=str(coverage.get("status") or "unavailable"),
    )
    direction = (
        "RISING" if change_bps is not None and change_bps >= NOTABLE_CHANGE_BPS
        else "FALLING" if change_bps is not None and change_bps <= -NOTABLE_CHANGE_BPS
        else "STABLE"
    )
    is_notable = direction != "STABLE"
    is_unusual = change_bps is not None and abs(change_bps) >= UNUSUAL_CHANGE_BPS
    sample_points = 20 if len(rows) >= 7 and not missing else 10 if len(rows) >= MIN_SAMPLE_DAYS else 0
    movement_points = min(60, abs(change_bps) // 500) if change_bps is not None else 0
    freshness_points = 10 if not stale else 0
    baseline_points = 10 if baseline_views is not None and baseline_views >= MIN_BASELINE_VIEWS else 0
    rank_score = min(100, movement_points + sample_points + freshness_points + baseline_points)
    source_url = _source_url(candidate, article)
    evidence = {
        "daily": [
            {
                "date": row["date"],
                "views": row["views"],
                "observation_id": f"wikimedia:en.wikipedia.org:{article}:{row['date']}",
            }
            for row in rows
        ],
        "raw_hashes": sorted({str(value) for value in coverage.get("raw_hashes") or [] if value}),
    }
    evidence_digest = "sha256:" + sha256_text(
        canonical_json(
            {
                "source": SCOUT_SOURCE_ID,
                "article": article,
                "window_start": coverage.get("window_start"),
                "window_end": coverage.get("window_end"),
                "daily": evidence["daily"],
                "raw_hashes": evidence["raw_hashes"],
            }
        )
    )
    uncertainty: list[str] = []
    if missing:
        uncertainty.append("Missing daily observations remain unavailable; no values were imputed.")
    if baseline_views is None or baseline_views <= 0:
        uncertainty.append("The first observed value is zero or unavailable, so change bps is unavailable.")
    if stale:
        uncertainty.append(f"The stored observation is older than {STALE_AFTER_HOURS} hours.")
    if len(rows) < MIN_SAMPLE_DAYS:
        uncertainty.append(f"Only {len(rows)} daily observations are available; at least {MIN_SAMPLE_DAYS} are required.")
    item = {
        "candidate_id": candidate.get("candidate_id"),
        "canonical_topic_id": candidate.get("canonical_topic_id"),
        "topic": article,
        "source_article": article,
        "source_url": source_url,
        "source": {
            "id": SCOUT_SOURCE_ID,
            "project": SCOUT_PROJECT,
            "access": SCOUT_ACCESS,
            "agent": SCOUT_AGENT,
            "metric": "daily_pageviews",
            "article": article,
            "article_url": source_url,
            "api_url": pageviews_api_url(article, coverage.get("window_start") or "", coverage.get("window_end") or "") if start and end else None,
        },
        "observation_window": {
            "start": coverage.get("window_start"),
            "end": coverage.get("window_end"),
            "sample_count": len(rows),
            "expected_days": len(expected),
            "missing_days": missing,
            "minimum_sample_days": MIN_SAMPLE_DAYS,
        },
        "baseline": baseline,
        "current": current,
        "change": {
            "change_bps": change_bps,
            "change_percent": round(change_bps / 100, 2) if change_bps is not None else None,
            "absolute_views": current_views - baseline_views if current_views is not None and baseline_views is not None else None,
            "formula": "floor((current_views - baseline_views) * 10000 / baseline_views)",
        },
        "direction": direction,
        "is_notable": is_notable,
        "is_unusual": is_unusual,
        "freshness": {
            "observed_at": iso_utc(observed),
            "age_hours": age_hours,
            "stale_after_hours": STALE_AFTER_HOURS,
            "status": "STALE" if stale else "FRESH",
        },
        "evidence_digest": evidence_digest,
        "evidence": evidence,
        "existing_market_match": existing_market_match,
        "candidate_status": status,
        "uncertainty": uncertainty,
        "limitations": [
            "Wikimedia pageviews measure article attention, not social sentiment, intent, causality, or price direction.",
            "This movement is a research signal, not a published prediction market or settlement result.",
        ],
        "rank": {
            "score": rank_score,
            "version": SCOUT_VERSION,
            "components": {
                "movement": movement_points,
                "sample_quality": sample_points,
                "freshness": freshness_points,
                "baseline_quality": baseline_points,
            },
        },
    }
    item["proposal"] = _proposal(candidate, article, item)
    return item


def build_scout_feed(
    candidates: list[dict[str, Any]],
    *,
    now: datetime,
    existing_market_matches: dict[str, dict[str, Any]] | None = None,
    direction: str = "all",
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    direction = direction.upper()
    if direction not in {"ALL", "RISING", "FALLING"}:
        raise ValueError("direction must be all, rising, or falling")
    matches = existing_market_matches or {}
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        article = _article(candidate)
        key = normalize_name(article or "")
        item = build_scout_candidate(
            candidate,
            now=now,
            existing_market_match=matches.get(key),
        )
        if item is None or (direction != "ALL" and item["direction"] != direction):
            continue
        topic_key = normalize_name(str(item.get("canonical_topic_id") or item["topic"]))
        previous = unique.get(topic_key)
        if previous is None or (
            -int(item["rank"]["score"]), str(item["candidate_id"])
        ) < (
            -int(previous["rank"]["score"]), str(previous["candidate_id"])
        ):
            unique[topic_key] = item
    result = list(unique.values())
    result.sort(
        key=lambda item: (
            -int(item["rank"]["score"]),
            -abs(int(item["change"].get("change_bps") or 0)),
            str(item["candidate_id"]),
        )
    )
    return result[: max(1, min(int(limit), MAX_LIMIT))]


def scout_metadata() -> dict[str, Any]:
    return {
        "version": SCOUT_VERSION,
        "supported_topics": list(SUPPORTED_TOPICS),
        "source": SCOUT_SOURCE_ID,
        "formula": "floor((current_views - baseline_views) * 10000 / baseline_views)",
        "notable_change_bps": NOTABLE_CHANGE_BPS,
        "unusual_change_bps": UNUSUAL_CHANGE_BPS,
        "minimum_sample_days": MIN_SAMPLE_DAYS,
        "minimum_baseline_views": MIN_BASELINE_VIEWS,
        "stale_after_hours": STALE_AFTER_HOURS,
        "missing_data": "No imputation; incomplete and zero-baseline records remain review-only or unavailable.",
        "ranking": "movement=min(60, abs(change_bps)//500) + sample quality + freshness + baseline quality; deterministic tie-break by candidate id.",
    }
