"""Wikimedia Pageviews and MediaWiki identity adapter."""

from __future__ import annotations

import time
import urllib.parse
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any

from ..canonical import sha256_text
from ..http import FetchError
from ..models import (
    RawObservation,
    SettlementCoverage,
    SourceHealth,
    SourceResult,
    SourceStatus,
)

TOP_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
    "en.wikipedia.org/all-access/{year}/{month:02d}/{day:02d}"
)
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{article}/daily/{start}/{end}"
)

NON_TOPIC_PREFIXES = (
    "special:",
    "wikipedia:",
    "portal:",
    "help:",
    "file:",
    "category:",
    "template:",
    "talk:",
    "user:",
    "draft:",
    "module:",
    "mediawiki:",
    "book:",
    "timedtext:",
    "gadget:",
    "gadget definition:",
)
NON_TOPIC_TITLE_PREFIXES = (
    "list of ",
    "deaths in ",
    "timeline of ",
    "index of ",
    "outline of ",
    "glossary of ",
    "bibliography of ",
    "list_of_",
    "deaths_in_",
    "timeline_of_",
    "index_of_",
    "outline_of_",
    "glossary_of_",
)


def _display_article(raw: str) -> str:
    return urllib.parse.unquote(raw).replace("_", " ").strip()


def is_topic_article(article: str, pageprops: dict[str, Any] | None = None) -> bool:
    display = _display_article(article)
    lower = display.casefold()
    if not display or display == "-":
        return False
    if lower in {"main page", "404.php", "index.php", "undefined"}:
        return False
    if lower.startswith(NON_TOPIC_PREFIXES):
        return False
    if lower.startswith(NON_TOPIC_TITLE_PREFIXES):
        return False
    if "(disambiguation)" in lower:
        return False
    if pageprops and "disambiguation" in pageprops:
        return False
    return True


class WikimediaAdapter:
    source = "wikimedia"

    def __init__(
        self,
        fetcher: Any,
        *,
        top_limit: int = 40,
        min_views: int = 10_000,
        min_baseline_views: int = 1_000,
        cache_ttl_seconds: int = 6 * 60 * 60,
    ) -> None:
        self.fetcher = fetcher
        self.top_limit = top_limit
        self.min_views = min_views
        self.min_baseline_views = min_baseline_views
        self.cache_ttl_seconds = cache_ttl_seconds

    def fetch(self, now: datetime, scan_date: date) -> SourceResult:
        started = time.monotonic()
        attempted_at = now
        last_error: FetchError | None = None
        top_result = None
        top_date: date | None = None

        # Wikimedia daily data is usually published with a lag. Try yesterday
        # and two preceding complete UTC days, in order, exactly once each.
        for offset in range(3):
            candidate_day = scan_date - timedelta(days=1 + offset)
            url = TOP_URL.format(
                year=candidate_day.year,
                month=candidate_day.month,
                day=candidate_day.day,
            )
            try:
                result = self.fetcher.get_json(
                    url,
                    source=self.source,
                    cache_key=f"top/{candidate_day.isoformat()}",
                    ttl_seconds=self.cache_ttl_seconds,
                    allow_stale=True,
                )
            except FetchError as exc:
                last_error = exc
                if exc.status == 404:
                    continue
                break
            top_result = result
            top_date = candidate_day
            break

        if top_result is None:
            error = last_error.as_dict() if last_error else None
            return SourceResult(
                source=self.source,
                observations=[],
                health=SourceHealth(
                    source=self.source,
                    status=SourceStatus.FAILED,
                    attempted_at=attempted_at,
                    error=error["message"] if error else "no Wikimedia top data",
                    rate_limited=bool(error and error.get("kind") == "rate_limit"),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    detail="No complete daily top-articles response was available or cached.",
                ),
            )

        payload = top_result.data or {}
        items = payload.get("items") or []
        if not items:
            return SourceResult(
                source=self.source,
                observations=[],
                health=SourceHealth(
                    source=self.source,
                    status=SourceStatus.FAILED,
                    attempted_at=attempted_at,
                    error="Wikimedia response contained no items",
                    cache_used=top_result.from_cache,
                    stale=top_result.stale,
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )

        item = items[0]
        reporting_date = date(
            int(item["year"]), int(item["month"]), int(item["day"])
        )
        raw_articles = item.get("articles") or []
        filtered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in raw_articles:
            article = _display_article(str(entry.get("article", "")))
            if not is_topic_article(article):
                continue
            if int(entry.get("views", 0)) < self.min_views:
                continue
            key = article.casefold()
            if key in seen:
                continue
            seen.add(key)
            filtered.append(
                {
                    "article": article,
                    "views": int(entry.get("views", 0)),
                    "rank": int(entry.get("rank", 0)),
                }
            )
            if len(filtered) >= self.top_limit:
                break

        identity_map: dict[str, dict[str, Any]] = {}
        identity_error: str | None = None
        if filtered:
            identity_map, identity_error = self.resolve_articles(
                [entry["article"] for entry in filtered]
            )

        observed_at = datetime.combine(
            reporting_date, dt_time(23, 59, 59), tzinfo=timezone.utc
        )
        observations: list[RawObservation] = []
        for entry in filtered:
            identity = identity_map.get(entry["article"], {})
            resolved = identity.get("title") or entry["article"]
            page_id = identity.get("page_id")
            canonical_url = identity.get("canonical_url") or (
                "https://en.wikipedia.org/wiki/"
                + urllib.parse.quote(entry["article"].replace(" ", "_"), safe="()_,'")
            )
            observations.append(
                RawObservation(
                    source=self.source,
                    source_id=f"wikimedia:en.wikipedia.org:{resolved}",
                    title=resolved,
                    url=canonical_url,
                    observed_at=observed_at,
                    metrics={
                        "views": entry["views"],
                        "rank": entry["rank"],
                        "reporting_date": reporting_date.isoformat(),
                        "project": "en.wikipedia.org",
                        "access": "all-access",
                        "agent": "user",
                        "article_original": entry["article"],
                        "article_resolved": resolved,
                        "page_id": page_id,
                    },
                    source_identity={
                        "source": self.source,
                        "project": "en.wikipedia.org",
                        "article_original": entry["article"],
                        "article_resolved": resolved,
                        "page_id": page_id,
                        "canonical_url": canonical_url,
                        "api_url": TOP_URL.format(
                            year=reporting_date.year,
                            month=reporting_date.month,
                            day=reporting_date.day,
                        ),
                        "redirected_from": identity.get("redirected_from"),
                    },
                    reporting_date=reporting_date,
                    raw_hash=top_result.raw_hash,
                    raw_ref=top_result.url,
                )
            )

        degraded = identity_error is not None or top_result.from_cache
        if top_result.stale:
            status = SourceStatus.DEGRADED
        elif top_result.from_cache:
            status = SourceStatus.CACHED
        elif identity_error:
            status = SourceStatus.DEGRADED
        else:
            status = SourceStatus.OK

        return SourceResult(
            source=self.source,
            observations=observations,
            context={
                "reporting_date": reporting_date.isoformat(),
                "requested_date": top_date.isoformat() if top_date else None,
                "top_url": top_result.url,
                "top_articles_seen": len(raw_articles),
                "filtered_articles": len(filtered),
                "access": "all-access",
                "agent": "user",
                "project": "en.wikipedia.org",
                "identity_error": identity_error,
                "note": (
                    "Wikimedia daily top articles for the latest complete reporting "
                    "day; this is historical daily data, not a live feed."
                ),
            },
            health=SourceHealth(
                source=self.source,
                status=status,
                attempted_at=attempted_at,
                last_success_at=top_result.fetched_at,
                error=identity_error,
                stale=top_result.stale,
                cache_used=top_result.from_cache,
                item_count=len(observations),
                latency_ms=int((time.monotonic() - started) * 1000),
                detail=(
                    "Cached response; source freshness is limited to the reporting day."
                    if top_result.from_cache
                    else "Live Wikimedia Pageviews top-articles response."
                ),
            ),
            identity_map=identity_map,
            snapshot=payload,
            snapshot_fetched_at=top_result.fetched_at,
            snapshot_hash=top_result.raw_hash,
            use_cached_snapshot=top_result.from_cache,
        )

    def resolve_articles(
        self, articles: list[str]
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        """Resolve titles, redirects and page IDs via one MediaWiki API call."""
        if not articles:
            return {}, None
        identity: dict[str, dict[str, Any]] = {}
        for start in range(0, len(articles), 50):
            batch = articles[start : start + 50]
            params = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "redirects": "1",
                "prop": "info|pageprops",
                "titles": "|".join(batch),
            }
            url = MEDIAWIKI_API + "?" + urllib.parse.urlencode(params)
            try:
                result = self.fetcher.get_json(
                    url,
                    source=self.source,
                    cache_key="identity/" + sha256_text(url)[:24],
                    ttl_seconds=self.cache_ttl_seconds,
                    allow_stale=True,
                )
            except FetchError as exc:
                return identity, exc.as_dict()["message"]
            except Exception as exc:
                return identity, f"identity resolution error: {exc}"

            data = result.data or {}
            query = data.get("query") or {}
            normalized = {
                self._identity_key(item["from"]): self._identity_key(item["to"])
                for item in query.get("normalized", [])
                if item.get("from") and item.get("to")
            }
            redirects = {
                self._identity_key(item["from"]): self._identity_key(item["to"])
                for item in query.get("redirects", [])
                if item.get("from") and item.get("to")
            }
            pages = {
                self._identity_key(page.get("title", "")): page
                for page in query.get("pages", [])
                if page.get("title")
            }
            for requested in batch:
                key = self._identity_key(requested)
                seen: set[str] = set()
                for _ in range(6):
                    if key in seen:
                        break
                    seen.add(key)
                    if key in normalized:
                        key = normalized[key]
                    elif key in redirects:
                        key = redirects[key]
                    else:
                        break
                page = pages.get(key)
                if not page or page.get("missing"):
                    continue
                title = page.get("title") or requested
                identity[requested] = {
                    "title": title,
                    "page_id": page.get("pageid"),
                    "redirected_from": (
                        requested if self._identity_key(title) != self._identity_key(requested) else None
                    ),
                    "canonical_url": "https://en.wikipedia.org/wiki/"
                    + urllib.parse.quote(title.replace(" ", "_"), safe="()_,'"),
                    "pageprops": page.get("pageprops") or {},
                }
        return identity, None

    def probe_pageviews(
        self,
        *,
        article: str,
        page_id: int | None,
        end_date: date,
        days: int = 7,
    ) -> SettlementCoverage:
        start_date = end_date - timedelta(days=days - 1)
        article_path = urllib.parse.quote(
            article.replace(" ", "_"), safe="()_,'"
        )
        url = PAGEVIEWS_URL.format(
            article=article_path,
            start=start_date.strftime("%Y%m%d"),
            end=end_date.strftime("%Y%m%d"),
        )
        coverage = SettlementCoverage(
            article=article,
            page_id=page_id,
            window_start=start_date.isoformat(),
            window_end=end_date.isoformat(),
            min_baseline_views=self.min_baseline_views,
            notes=[
                "Daily Wikimedia pageviews, all-access/user, UTC full days.",
                "This is an eligibility probe, not finalized settlement evidence.",
            ],
        )
        try:
            result = self.fetcher.get_json(
                url,
                source=self.source,
                cache_key=f"pageviews/{article_path}/{start_date}/{end_date}",
                ttl_seconds=self.cache_ttl_seconds,
                allow_stale=True,
            )
        except FetchError as exc:
            coverage.status = "not_found" if exc.status == 404 else "error"
            coverage.error = exc.as_dict()["message"]
            return coverage
        except Exception as exc:
            coverage.status = "error"
            coverage.error = f"pageviews probe error: {exc}"
            return coverage

        items = (result.data or {}).get("items") or []
        daily: list[dict[str, Any]] = []
        for item in items:
            timestamp = str(item.get("timestamp", ""))
            if len(timestamp) < 8:
                continue
            day = timestamp[:8]
            if day < start_date.strftime("%Y%m%d") or day > end_date.strftime("%Y%m%d"):
                continue
            daily.append(
                {
                    "date": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                    "views": int(item.get("views", 0)),
                    "timestamp": timestamp,
                }
            )
        daily.sort(key=lambda value: value["date"])
        coverage.daily_views = daily
        coverage.raw_hashes = [result.raw_hash]
        if not daily:
            coverage.status = "not_found"
            coverage.error = "no daily observations returned for the requested window"
            return coverage
        if len(daily) < 5:
            coverage.status = "incomplete"
            coverage.error = f"only {len(daily)} daily observations returned"
            return coverage
        coverage.min_views = min(item["views"] for item in daily)
        coverage.mean_views = sum(item["views"] for item in daily) // len(daily)
        if coverage.min_views < self.min_baseline_views:
            coverage.status = "insufficient_baseline"
            coverage.error = (
                f"minimum daily views {coverage.min_views} is below "
                f"the {self.min_baseline_views} minimum"
            )
        else:
            coverage.status = "ok"
        return coverage

    @staticmethod
    def _identity_key(value: str) -> str:
        return _display_article(value).casefold()
