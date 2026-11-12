"""Wikimedia Pageviews observation retrieval for the deterministic oracle."""

from __future__ import annotations

import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any

from services.trend_radar.canonical import canonical_json, normalize_name, sha256_text
from services.trend_radar.http import FetchError
from services.trend_radar.sources.wikimedia import WikimediaAdapter

from .models import DayObservation, PageviewsRange

PROJECT = "en.wikipedia.org"
ACCESS = "all-access"
AGENT = "user"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{article}/daily/{start}/{end}"
)
PAGEVIEWS_TTL_SECONDS = 24 * 60 * 60


def _article_path(article: str) -> str:
    return urllib.parse.quote(article.replace(" ", "_"), safe="()_,'")


def pageviews_url(article: str, start: date, end: date) -> str:
    return PAGEVIEWS_URL.format(
        article=_article_path(article),
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )


def date_range(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def observation_hash(observation: DayObservation) -> str:
    return sha256_text(
        canonical_json(
            {
                "date": observation.date,
                "views": observation.views,
                "timestamp": observation.timestamp,
            }
        )
    )


def resolve_article_identity(fetcher: Any, article: str) -> dict[str, Any] | None:
    """Resolve page ID and redirects through the S3A MediaWiki helper."""
    identity, _error = WikimediaAdapter(fetcher).resolve_articles([article])
    return identity.get(article)


def fetch_range(
    fetcher: Any,
    *,
    article: str,
    start_date: date,
    end_date: date,
    project: str = PROJECT,
    cache_ttl_seconds: int = PAGEVIEWS_TTL_SECONDS,
) -> PageviewsRange:
    url = pageviews_url(article, start_date, end_date)
    result = PageviewsRange(
        article=article,
        project=project,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_url=url,
    )
    try:
        fetched = fetcher.get_json(
            url,
            source="wikimedia",
            cache_key=f"oracle/pageviews/{_article_path(article)}/{start_date}/{end_date}",
            ttl_seconds=cache_ttl_seconds,
            allow_stale=False,
        )
    except FetchError as exc:
        result.error = exc.as_dict()["message"]
        result.raw_response_hash = ""
        result.retrieved_at = None
        return result
    except Exception as exc:  # defensive isolation
        result.error = f"pageviews fetch error: {exc}"
        return result

    result.raw_response_hash = fetched.raw_hash
    result.retrieved_at = fetched.fetched_at
    payload = fetched.data or {}
    items = payload.get("items")
    if not isinstance(items, list):
        result.error = "pageviews response missing items array"
        return result

    requested = [day.isoformat() for day in date_range(start_date, end_date)]
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            result.item_errors.append("non-object item")
            continue
        timestamp = str(item.get("timestamp", ""))
        if len(timestamp) < 8:
            result.item_errors.append(f"bad timestamp: {timestamp!r}")
            continue
        day = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        try:
            views = int(item.get("views"))
        except (TypeError, ValueError):
            result.item_errors.append(f"bad views for {day}")
            continue
        if views < 0:
            result.item_errors.append(f"negative views for {day}")
            continue
        item_project = str(item.get("project", ""))
        if item_project not in {"en.wikipedia", PROJECT}:
            result.item_errors.append(f"unexpected project for {day}: {item_project}")
            continue
        if normalize_name(str(item.get("article", ""))) != normalize_name(article):
            result.item_errors.append(f"unexpected article for {day}")
            continue
        if item.get("access") != ACCESS:
            result.item_errors.append(f"unexpected access for {day}")
            continue
        if item.get("agent") != AGENT:
            result.item_errors.append(f"unexpected agent for {day}")
            continue
        if item.get("granularity") != "daily":
            result.item_errors.append(f"unexpected granularity for {day}")
            continue
        if day in seen:
            if day not in result.duplicate_dates:
                result.duplicate_dates.append(day)
            continue
        seen.add(day)
        observation = DayObservation(
            date=day,
            views=views,
            timestamp=timestamp,
            observation_hash="",
            raw_response_hash=fetched.raw_hash,
            retrieved_at=fetched.fetched_at,
            source_url=url,
            project=project,
            article=article,
            access=ACCESS,
            agent=AGENT,
        )
        observation.observation_hash = observation_hash(observation)
        result.observations[day] = observation

    result.missing_dates = [day for day in requested if day not in result.observations]
    if result.item_errors and not result.error:
        result.error = "; ".join(result.item_errors[:5])
    return result


def get_day(range_result: PageviewsRange, day: date) -> DayObservation | None:
    return range_result.observations.get(day.isoformat())


def latest_complete_day(now: datetime) -> date:
    return now.date() - timedelta(days=1)
