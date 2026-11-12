"""Hacker News (Algolia) front-page discovery adapter.

Hacker News is a discovery source only. Points and comments are discussion
signals, not settlement measurements.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..models import RawObservation, SourceHealth, SourceResult, SourceStatus

FRONT_PAGE_URL = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={story_id}"

SKIP_TITLE_PREFIXES = ("ask hn:", "show hn:", "tell hn:", "launch hn:")


class HackerNewsAdapter:
    source = "hackernews"

    def __init__(
        self,
        fetcher: Any,
        *,
        cache_ttl_seconds: int = 180,
        max_stories: int = 30,
    ) -> None:
        self.fetcher = fetcher
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_stories = max_stories

    def fetch(self, now: datetime, scan_date) -> SourceResult:
        del scan_date
        started = time.monotonic()
        try:
            result = self.fetcher.get_json(
                FRONT_PAGE_URL,
                source=self.source,
                cache_key="front_page",
                ttl_seconds=self.cache_ttl_seconds,
                allow_stale=True,
            )
        except Exception as exc:
            kind = getattr(exc, "kind", "unknown")
            return SourceResult(
                source=self.source,
                observations=[],
                health=SourceHealth(
                    source=self.source,
                    status=SourceStatus.FAILED,
                    attempted_at=now,
                    error=str(exc),
                    rate_limited=kind == "rate_limit",
                    latency_ms=int((time.monotonic() - started) * 1000),
                    detail="Hacker News failed independently; other sources continue.",
                ),
            )

        payload = result.data or {}
        hits = payload.get("hits") or []
        observations: list[RawObservation] = []
        indexing_ages: list[int] = []
        for hit in hits[: self.max_stories]:
            story_id = str(hit.get("objectID") or "").strip()
            title = str(hit.get("title") or "").strip()
            if not story_id or not title:
                continue
            if title.casefold().startswith(SKIP_TITLE_PREFIXES):
                continue
            created_at_i = hit.get("created_at_i")
            try:
                created_epoch = int(created_at_i) if created_at_i is not None else None
            except (TypeError, ValueError):
                created_epoch = None
            created_at = (
                datetime.fromtimestamp(created_epoch, tz=timezone.utc)
                if created_epoch is not None
                else None
            )
            if created_epoch is not None:
                indexing_ages.append(max(0, int(now.timestamp()) - created_epoch))
            story_url = str(hit.get("url") or "").strip()
            hn_url = HN_ITEM_URL.format(story_id=story_id)
            observations.append(
                RawObservation(
                    source=self.source,
                    source_id=f"hn:story:{story_id}",
                    title=title,
                    url=story_url or hn_url,
                    observed_at=result.fetched_at,
                    metrics={
                        "points": hit.get("points"),
                        "comments": hit.get("num_comments"),
                        "created_at_i": created_epoch,
                        "author": hit.get("author"),
                        "hn_url": hn_url,
                        "story_url": story_url or None,
                    },
                    source_identity={
                        "source": self.source,
                        "story_id": story_id,
                        "title": title,
                        "url": story_url or hn_url,
                        "hn_url": hn_url,
                        "created_at": created_at.isoformat().replace("+00:00", "Z")
                        if created_at
                        else None,
                        "points": hit.get("points"),
                        "comments": hit.get("num_comments"),
                    },
                    raw_hash=result.raw_hash,
                    raw_ref=result.url,
                )
            )

        status = SourceStatus.CACHED if result.from_cache and not result.stale else (
            SourceStatus.DEGRADED if result.stale else SourceStatus.OK
        )
        max_age = max(indexing_ages) if indexing_ages else None
        return SourceResult(
            source=self.source,
            observations=observations,
            context={
                "front_page_hits": len(hits),
                "max_story_age_seconds": max_age,
                "note": (
                    "Algolia front-page index; points and comments are discussion "
                    "signals and may lag the live HN front page."
                ),
            },
            health=SourceHealth(
                source=self.source,
                status=status,
                attempted_at=now,
                last_success_at=result.fetched_at,
                stale=result.stale,
                cache_used=result.from_cache,
                item_count=len(observations),
                latency_ms=int((time.monotonic() - started) * 1000),
                detail=(
                    "Using cached Hacker News response."
                    if result.from_cache
                    else "Live Hacker News Algolia front-page response."
                ),
            ),
            snapshot=payload,
            snapshot_fetched_at=result.fetched_at,
            snapshot_hash=result.raw_hash,
            use_cached_snapshot=result.from_cache,
        )
