import email.message
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from services.trend_radar.http import (
    FetchError,
    FixtureFetcher,
    LiveFetcher,
    RateLimiter,
)

URL = "https://example.test/data"
NOW = datetime(2026, 11, 11, 23, 45, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, data, status=200):
        self._raw = json.dumps(data).encode("utf-8") if not isinstance(data, bytes) else data
        self.status = status
        self.headers = {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def http_error(code, retry_after=None, body=b"error"):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError(URL, code, "error", headers, io.BytesIO(body))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "radar"
        self.now = NOW
        self.calls = 0

    def tearDown(self):
        self.temp.cleanup()

    def fetcher(self, **kwargs):
        return LiveFetcher(
            self.data_dir,
            now_fn=lambda: self.now,
            sleep=lambda _seconds: None,
            rate_limiter=RateLimiter(
                {"test": 0.0}, clock=lambda: 0.0, sleep=lambda _seconds: None
            ),
            **kwargs,
        )

    def test_fresh_cache_short_circuits_and_stale_cache_falls_back(self):
        def fake_urlopen(request, timeout=None):
            self.calls += 1
            return FakeResponse({"value": self.calls})

        with mock.patch(
            "services.trend_radar.http.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            fetcher = self.fetcher()
            first = fetcher.get_json(URL, source="test", ttl_seconds=60)
            self.assertFalse(first.from_cache)
            self.assertEqual(first.data, {"value": 1})
            second = fetcher.get_json(URL, source="test", ttl_seconds=60)
            self.assertTrue(second.from_cache)
            self.assertFalse(second.stale)
            self.assertEqual(self.calls, 1)

            self.now = NOW + timedelta(seconds=61)
            with mock.patch(
                "services.trend_radar.http.urllib.request.urlopen",
                side_effect=urllib.error.URLError("down"),
            ):
                stale = fetcher.get_json(URL, source="test", ttl_seconds=60)
            self.assertTrue(stale.from_cache)
            self.assertTrue(stale.stale)
            self.assertEqual(stale.data, {"value": 1})
            self.assertEqual(self.calls, 1)

    def test_5xx_retries_bounded(self):
        responses = [
            http_error(500),
            http_error(503),
            FakeResponse({"ok": True}),
        ]

        def fake_urlopen(request, timeout=None):
            self.calls += 1
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch(
            "services.trend_radar.http.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            fetcher = self.fetcher(max_retries=2)
            result = fetcher.get_json(URL, source="test", ttl_seconds=60)
        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(self.calls, 3)

    def test_rate_limit_retry_after_is_honored(self):
        responses = [http_error(429, retry_after=0), FakeResponse({"ok": True})]

        def fake_urlopen(request, timeout=None):
            self.calls += 1
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch(
            "services.trend_radar.http.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            fetcher = self.fetcher(max_retries=1)
            result = fetcher.get_json(URL, source="test", ttl_seconds=60)
        self.assertEqual(result.data, {"ok": True})
        self.assertEqual(self.calls, 2)

    def test_rate_limit_exhaustion_raises(self):
        with mock.patch(
            "services.trend_radar.http.urllib.request.urlopen",
            side_effect=http_error(429, retry_after=0),
        ):
            fetcher = self.fetcher(max_retries=1)
            with self.assertRaises(FetchError) as context:
                fetcher.get_json(URL, source="test", ttl_seconds=60)
        self.assertEqual(context.exception.kind, "rate_limit")
        self.assertEqual(context.exception.status, 429)

    def test_invalid_json_is_not_retried(self):
        with mock.patch(
            "services.trend_radar.http.urllib.request.urlopen",
            return_value=FakeResponse(b"not json"),
        ) as opener:
            fetcher = self.fetcher(max_retries=2)
            with self.assertRaises(FetchError) as context:
                fetcher.get_json(URL, source="test", ttl_seconds=60)
        self.assertEqual(context.exception.kind, "invalid_json")
        self.assertEqual(opener.call_count, 1)

    def test_rate_limiter_sleeps_for_interval(self):
        clock_value = [0.0]
        sleeps = []

        def clock():
            return clock_value[0]

        def sleep(seconds):
            sleeps.append(seconds)
            clock_value[0] += seconds

        limiter = RateLimiter({"test": 0.2}, clock=clock, sleep=sleep)
        limiter.wait("test")
        limiter.wait("test")
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 0.2, places=6)

    def test_fixture_fetcher_loads_top_and_missing_pageviews_is_404(self):
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        fetcher = FixtureFetcher(fixtures, now_fn=lambda: NOW)
        top = fetcher.get_json(
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia.org/all-access/2026/11/10",
            source="wikimedia",
        )
        self.assertIn("items", top.data)
        with self.assertRaises(FetchError) as context:
            fetcher.get_json(
                "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Unknown/daily/20261104/20261110",
                source="wikimedia",
            )
        self.assertEqual(context.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
