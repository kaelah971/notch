"""HTTP, cache, retries and rate limiting for the Trend Radar.

All HTTP is bounded. A failure never fabricates data: the fetcher either
returns a real cached response or raises.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .canonical import canonical_json, sha256_bytes
from .models import iso_utc, now_utc, parse_iso


DEFAULT_USER_AGENT = (
    "NotchTrendRadar/0.1 (NEAR testnet discovery; local development)"
)


class FetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        url: str,
        kind: str = "http",
        status: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        body_snippet: str | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.kind = kind
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after
        self.body_snippet = body_snippet

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "url": self.url,
            "kind": self.kind,
            "status": self.status,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "body_snippet": self.body_snippet,
        }


@dataclass
class FetchResult:
    data: Any
    url: str
    source: str
    fetched_at: datetime
    raw_hash: str
    from_cache: bool = False
    stale: bool = False
    status_code: int = 200
    cache_age_seconds: float | None = None
    cache_path: str | None = None


class RateLimiter:
    """Simple per-source minimum request interval."""

    def __init__(
        self,
        intervals: dict[str, float] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.intervals = intervals or {
            "wikimedia": 0.2,
            "coingecko": 1.0,
            "hackernews": 0.2,
        }
        self.clock = clock
        self.sleep = sleep
        self.last_request: dict[str, float] = {}

    def wait(self, source: str) -> float:
        interval = self.intervals.get(source, 0.0)
        now = self.clock()
        last = self.last_request.get(source)
        slept = 0.0
        if last is not None and interval > 0:
            remaining = interval - (now - last)
            if remaining > 0:
                self.sleep(remaining)
                slept = remaining
                now = self.clock()
        self.last_request[source] = now
        return slept


class FileCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, source: str, url: str, cache_key: str = "") -> Path:
        key = sha256_bytes(f"{source}|{url}|{cache_key}".encode("utf-8"))
        return self.root / source / f"{key}.json"

    def read(self, source: str, url: str, cache_key: str = "") -> dict[str, Any] | None:
        path = self._path(source, url, cache_key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        payload["cache_path"] = str(path)
        return payload

    def write(
        self,
        source: str,
        url: str,
        cache_key: str,
        *,
        body: Any,
        raw_text: str,
        raw_hash: str,
        fetched_at: datetime,
        status_code: int = 200,
    ) -> Path:
        path = self._path(source, url, cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "url": url,
            "cache_key": cache_key,
            "fetched_at": iso_utc(fetched_at),
            "raw_hash": raw_hash,
            "status_code": status_code,
            "raw_text": raw_text,
            "body": body,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path


class LiveFetcher:
    def __init__(
        self,
        data_dir: str | Path,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 12.0,
        max_retries: int = 2,
        rate_limiter: RateLimiter | None = None,
        now_fn: Callable[[], datetime] = now_utc,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.rate_limiter = rate_limiter or RateLimiter(sleep=sleep)
        self.now_fn = now_fn
        self.sleep = sleep
        self.cache = FileCache(self.data_dir / "cache")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def get_json(
        self,
        url: str,
        *,
        source: str,
        cache_key: str = "",
        ttl_seconds: int = 300,
        allow_stale: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> FetchResult:
        now = self.now_fn()
        cached = self.cache.read(source, url, cache_key)
        if cached:
            cached_at = parse_iso(cached.get("fetched_at"))
            age = (
                (now - cached_at).total_seconds()
                if cached_at is not None
                else None
            )
            if age is not None and age <= ttl_seconds:
                return FetchResult(
                    data=cached.get("body"),
                    url=url,
                    source=source,
                    fetched_at=cached_at,
                    raw_hash=cached.get("raw_hash") or "",
                    from_cache=True,
                    stale=False,
                    status_code=int(cached.get("status_code", 200)),
                    cache_age_seconds=age,
                    cache_path=cached.get("cache_path"),
                )

        last_error: FetchError | None = None
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait(source)
            request = urllib.request.Request(url, headers=self._headers(extra_headers))
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    raw = response.read()
                    body = json.loads(raw.decode("utf-8"))
                    fetched_at = self.now_fn()
                    raw_hash = sha256_bytes(raw)
                    path = self.cache.write(
                        source,
                        url,
                        cache_key,
                        body=body,
                        raw_text=raw.decode("utf-8"),
                        raw_hash=raw_hash,
                        fetched_at=fetched_at,
                        status_code=getattr(response, "status", 200),
                    )
                    return FetchResult(
                        data=body,
                        url=url,
                        source=source,
                        fetched_at=fetched_at,
                        raw_hash=raw_hash,
                        status_code=getattr(response, "status", 200),
                        cache_path=str(path),
                    )
            except urllib.error.HTTPError as exc:
                snippet = ""
                try:
                    snippet = exc.read()[:300].decode("utf-8", "replace")
                except Exception:
                    pass
                retry_after_raw = exc.headers.get("Retry-After") if exc.headers else None
                retry_after: float | None = None
                if retry_after_raw:
                    try:
                        retry_after = float(retry_after_raw)
                    except ValueError:
                        retry_after = None
                if exc.code == 429:
                    last_error = FetchError(
                        "rate limited by source",
                        url=url,
                        kind="rate_limit",
                        status=429,
                        retryable=True,
                        retry_after=retry_after,
                        body_snippet=snippet,
                    )
                    if attempt < self.max_retries:
                        wait_for = retry_after if retry_after is not None else 1.0
                        if wait_for > 5.0:
                            break
                        self.sleep(wait_for)
                        continue
                    break
                if 500 <= exc.code < 600 and attempt < self.max_retries:
                    last_error = FetchError(
                        f"source returned HTTP {exc.code}",
                        url=url,
                        kind="http",
                        status=exc.code,
                        retryable=True,
                        body_snippet=snippet,
                    )
                    self.sleep(min(0.5 * (2**attempt), 2.0))
                    continue
                last_error = FetchError(
                    f"source returned HTTP {exc.code}",
                    url=url,
                    kind="http",
                    status=exc.code,
                    retryable=False,
                    body_snippet=snippet,
                )
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = FetchError(
                    f"network error: {exc}",
                    url=url,
                    kind="network",
                    retryable=True,
                )
                if attempt < self.max_retries:
                    self.sleep(min(0.5 * (2**attempt), 2.0))
                    continue
                break
            except (UnicodeDecodeError, ValueError) as exc:
                last_error = FetchError(
                    f"invalid JSON response: {exc}",
                    url=url,
                    kind="invalid_json",
                    retryable=False,
                )
                break

        assert last_error is not None
        if allow_stale and cached:
            cached_at = parse_iso(cached.get("fetched_at"))
            age = (
                (now - cached_at).total_seconds()
                if cached_at is not None
                else None
            )
            return FetchResult(
                data=cached.get("body"),
                url=url,
                source=source,
                fetched_at=cached_at or now,
                raw_hash=cached.get("raw_hash") or "",
                from_cache=True,
                stale=True,
                status_code=int(cached.get("status_code", 200)),
                cache_age_seconds=age,
                cache_path=cached.get("cache_path"),
            )
        raise last_error


class FixtureFetcher:
    """Offline replay fetcher backed by recorded API responses."""

    def __init__(
        self,
        fixtures_dir: str | Path,
        *,
        now_fn: Callable[[], datetime] = now_utc,
    ) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.now_fn = now_fn
        manifest_path = self.fixtures_dir / "manifest.json"
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def _load(self, name: str) -> Any:
        path = self.fixtures_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def _fetched_at(self) -> datetime:
        value = self.manifest.get("fetched_at")
        if value:
            parsed = parse_iso(value)
            if parsed:
                return parsed
        return self.now_fn()

    def _result(self, data: Any, url: str, source: str) -> FetchResult:
        text = canonical_json(data)
        return FetchResult(
            data=data,
            url=url,
            source=source,
            fetched_at=self._fetched_at(),
            raw_hash=sha256_bytes(text.encode("utf-8")),
            from_cache=False,
            stale=False,
            status_code=200,
        )

    def get_json(
        self,
        url: str,
        *,
        source: str,
        cache_key: str = "",
        ttl_seconds: int = 300,
        allow_stale: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> FetchResult:
        del extra_headers
        if "/metrics/pageviews/top/" in url:
            name = self.manifest.get("wikimedia_top")
            if not name:
                raise FetchError("no wikimedia top fixture", url=url, kind="not_found", status=404)
            return self._result(self._load(name), url, source)

        if "wikipedia.org/w/api.php" in url:
            name = self.manifest.get("mediawiki_query")
            if not name:
                raise FetchError("no mediawiki query fixture", url=url, kind="not_found", status=404)
            return self._result(self._load(name), url, source)

        if "/metrics/pageviews/per-article/" in url:
            parsed = urllib.parse.urlparse(url)
            match = re.search(
                r"/per-article/[^/]+/[^/]+/[^/]+/(.+)/daily/", parsed.path
            )
            article = urllib.parse.unquote(match.group(1)) if match else ""
            pageviews = self.manifest.get("pageviews", {})
            name = pageviews.get(article)
            if not name:
                # allow underscore/space variants in fixture manifests
                alt = article.replace("_", " ")
                name = pageviews.get(alt)
            if not name:
                raise FetchError(
                    f"no pageviews fixture for {article}",
                    url=url,
                    kind="not_found",
                    status=404,
                )
            return self._result(self._load(name), url, source)

        if "api.coingecko.com" in url and "/search/trending" in url:
            name = self.manifest.get("coingecko_trending")
            if not name:
                raise FetchError("no coingecko trending fixture", url=url, kind="not_found", status=404)
            return self._result(self._load(name), url, source)

        if "api.coingecko.com" in url and "/coins/categories" in url:
            name = self.manifest.get("coingecko_categories")
            if not name:
                raise FetchError("no coingecko categories fixture", url=url, kind="not_found", status=404)
            return self._result(self._load(name), url, source)

        if "hn.algolia.com" in url:
            name = self.manifest.get("hackernews_front")
            if not name:
                raise FetchError("no hackernews fixture", url=url, kind="not_found", status=404)
            return self._result(self._load(name), url, source)

        raise FetchError(f"no fixture for URL: {url}", url=url, kind="not_found", status=404)


def make_fetcher(
    mode: str,
    *,
    data_dir: str | Path,
    fixtures_dir: str | Path | None = None,
    user_agent: str | None = None,
    now_fn: Callable[[], datetime] = now_utc,
    sleep: Callable[[float], None] = time.sleep,
) -> LiveFetcher | FixtureFetcher:
    if mode == "fixture":
        if not fixtures_dir:
            raise ValueError("fixture mode requires a fixtures directory")
        return FixtureFetcher(fixtures_dir, now_fn=now_fn)
    return LiveFetcher(
        data_dir,
        user_agent=user_agent or os.environ.get("RADAR_USER_AGENT") or DEFAULT_USER_AGENT,
        timeout_seconds=float(os.environ.get("RADAR_HTTP_TIMEOUT_SECONDS", "12")),
        max_retries=int(os.environ.get("RADAR_MAX_RETRIES", "2")),
        now_fn=now_fn,
        sleep=sleep,
    )
