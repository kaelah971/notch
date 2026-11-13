"""Bounded, provenance-preserving Wikimedia observations for market research."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from services.oracle.wikimedia import fetch_range, latest_complete_day
from services.trend_radar.models import iso_utc


MAX_RESEARCH_DAYS = 31
RECENT_RESEARCH_DAYS = 14


def _parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _articles(rule: dict[str, Any]) -> list[str]:
    topics = rule.get("topics") or []
    names = [str(item.get("article_title")) for item in topics if item.get("article_title")]
    if names:
        return list(dict.fromkeys(names))
    article = (rule.get("source") or {}).get("article")
    return [str(article)] if article else []


def _observation_window(rule: dict[str, Any], latest: date) -> tuple[date, date]:
    observation = rule.get("observation") or {}
    reference_days = [
        day
        for day in (_parse_day(observation.get("baseline_date")), _parse_day(observation.get("target_date")))
        if day is not None
    ]
    if reference_days and max(reference_days) <= latest:
        start = min(reference_days) - timedelta(days=7)
        end = max(reference_days)
    else:
        end = latest
        start = latest - timedelta(days=RECENT_RESEARCH_DAYS - 1)
    if end < start:
        start, end = end, start
    if (end - start).days + 1 > MAX_RESEARCH_DAYS:
        start = end - timedelta(days=MAX_RESEARCH_DAYS - 1)
    return start, end


def _snapshot(article: str, result: Any) -> dict[str, Any]:
    observations = [
        {
            "date": item.date,
            "timestamp": item.timestamp,
            "views": item.views,
            "observation_hash": item.observation_hash,
            "raw_response_hash": item.raw_response_hash,
            "retrieved_at": iso_utc(item.retrieved_at),
            "source_url": item.source_url,
            "source_id": f"wikimedia:{item.project}:{article}:{item.date}",
        }
        for item in sorted(result.observations.values(), key=lambda item: item.date)
    ]
    return {
        "article": article,
        "project": result.project,
        "access": "all-access",
        "agent": "user",
        "source_url": result.source_url,
        "window_start": result.start_date,
        "window_end": result.end_date,
        "observations": observations,
        "missing_dates": list(result.missing_dates),
        "raw_response_hash": result.raw_response_hash or None,
        "retrieved_at": iso_utc(result.retrieved_at) if result.retrieved_at else None,
        "error": result.error,
        "source_status": "parsed" if result.error is None and not result.item_errors and not result.missing_dates and not result.duplicate_dates else "incomplete",
        "item_errors": list(result.item_errors),
    }


def fetch_market_observations(
    rule_record: dict[str, Any],
    *,
    fetcher: Any,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Fetch only a small, complete-day window; never fill or infer missing rows."""
    rule = rule_record.get("rule", rule_record)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    latest = latest_complete_day(current)
    start, end = _observation_window(rule, latest)
    source = rule.get("source") or {}
    project = str(source.get("project") or "en.wikipedia.org")
    snapshots: list[dict[str, Any]] = []
    for article in _articles(rule):
        result = fetch_range(
            fetcher,
            article=article,
            start_date=start,
            end_date=end,
            project=project,
        )
        snapshots.append(_snapshot(article, result))
    return snapshots
