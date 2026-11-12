"""Offline fixture fetcher that preserves raw fixture bytes for hashing."""

from __future__ import annotations

import dataclasses
import hashlib
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from services.trend_radar.http import FetchResult, FixtureFetcher


class OracleFixtureFetcher:
    """Wrapper around S3A's fixture fetcher with raw-byte hashes.

    S3A hashes canonical JSON for discovery. S3B evidence needs the hash of the
    actual recorded API response bytes, so replay digests match live fetches of
    the same response.
    """

    def __init__(self, fixtures_dir: str | Path, *, now_fn) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.wrapped = FixtureFetcher(self.fixtures_dir, now_fn=now_fn)
        self.manifest = self.wrapped.manifest

    def _path_for(self, url: str) -> Path | None:
        if "/metrics/pageviews/per-article/" in url:
            parsed = urllib.parse.urlparse(url)
            match = re.search(
                r"/per-article/[^/]+/[^/]+/[^/]+/(.+)/daily/", parsed.path
            )
            article = urllib.parse.unquote(match.group(1)) if match else ""
            pageviews = self.manifest.get("pageviews", {})
            name = pageviews.get(article) or pageviews.get(article.replace("_", " "))
            return self.fixtures_dir / name if name else None
        if "wikipedia.org/w/api.php" in url:
            name = self.manifest.get("mediawiki_query")
            return self.fixtures_dir / name if name else None
        if "/metrics/pageviews/top/" in url:
            name = self.manifest.get("wikimedia_top")
            return self.fixtures_dir / name if name else None
        if "api.coingecko.com" in url and "/search/trending" in url:
            name = self.manifest.get("coingecko_trending")
            return self.fixtures_dir / name if name else None
        if "hn.algolia.com" in url:
            name = self.manifest.get("hackernews_front")
            return self.fixtures_dir / name if name else None
        return None

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        result = self.wrapped.get_json(url, source=source, **kwargs)
        path = self._path_for(url)
        if path and path.exists():
            result = dataclasses.replace(
                result, raw_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            )
        return result
