"""CoinGecko trending-coins discovery adapter.

CoinGecko is a discovery source only. Price and market-cap changes are never
treated as social attention or as settlement measurements.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

from ..models import RawObservation, SourceHealth, SourceResult, SourceStatus

TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
COIN_URL = "https://www.coingecko.com/en/coins/{coin_id}"


class CoinGeckoAdapter:
    source = "coingecko"

    def __init__(
        self,
        fetcher: Any,
        *,
        cache_ttl_seconds: int = 300,
        max_coins: int = 30,
    ) -> None:
        self.fetcher = fetcher
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_coins = max_coins

    def fetch(self, now: datetime, scan_date) -> SourceResult:
        del scan_date
        started = time.monotonic()
        api_key = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
        headers = {"x-cg-demo-api-key": api_key} if api_key else None
        try:
            result = self.fetcher.get_json(
                TRENDING_URL,
                source=self.source,
                cache_key="trending/" + ("demo" if api_key else "public"),
                ttl_seconds=self.cache_ttl_seconds,
                allow_stale=True,
                extra_headers=headers,
            )
        except Exception as exc:  # FetchError or unexpected transport error
            message = str(exc)
            kind = getattr(exc, "kind", "unknown")
            status_code = getattr(exc, "status", None)
            return SourceResult(
                source=self.source,
                observations=[],
                health=SourceHealth(
                    source=self.source,
                    status=SourceStatus.FAILED,
                    attempted_at=now,
                    error=message,
                    rate_limited=kind == "rate_limit",
                    latency_ms=int((time.monotonic() - started) * 1000),
                    detail=(
                        "CoinGecko failed independently; other discovery sources "
                        "continue."
                    ),
                ),
            )

        payload = result.data or {}
        coins = payload.get("coins") or []
        categories = payload.get("categories") or []
        observations: list[RawObservation] = []
        for index, coin in enumerate(coins[: self.max_coins], start=1):
            item = coin.get("item") or {}
            coin_id = item.get("id")
            name = item.get("name")
            symbol = item.get("symbol")
            if not coin_id or not name:
                continue
            observations.append(
                RawObservation(
                    source=self.source,
                    source_id=f"coingecko:coin:{coin_id}",
                    title=str(name),
                    url=COIN_URL.format(coin_id=coin_id),
                    observed_at=result.fetched_at,
                    metrics={
                        "symbol": symbol,
                        "market_cap_rank": item.get("market_cap_rank"),
                        "trending_rank": index,
                        "coingecko_score": item.get("score"),
                    },
                    source_identity={
                        "source": self.source,
                        "coin_id": coin_id,
                        "symbol": symbol,
                        "name": name,
                        "market_cap_rank": item.get("market_cap_rank"),
                        "trending_rank": index,
                        "url": COIN_URL.format(coin_id=coin_id),
                    },
                    raw_hash=result.raw_hash,
                    raw_ref=result.url,
                )
            )

        context_categories = []
        for category in categories[:10]:
            context_categories.append(
                {
                    "id": category.get("id"),
                    "name": category.get("name"),
                    "market_cap_1h_change": category.get("market_cap_1h_change"),
                    "coins_count": category.get("coins_count"),
                }
            )

        status = SourceStatus.CACHED if result.from_cache and not result.stale else (
            SourceStatus.DEGRADED if result.stale else SourceStatus.OK
        )
        return SourceResult(
            source=self.source,
            observations=observations,
            context={
                "trending_coin_count": len(coins),
                "categories": context_categories,
                "note": (
                    "CoinGecko trending and category data are discovery context. "
                    "Price or market-cap movement is not social attention and is "
                    "never used as a settlement metric."
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
                    "Using cached CoinGecko response."
                    if result.from_cache
                    else "Live CoinGecko trending response."
                ),
            ),
            snapshot=payload,
            snapshot_fetched_at=result.fetched_at,
            snapshot_hash=result.raw_hash,
            use_cached_snapshot=result.from_cache,
        )
