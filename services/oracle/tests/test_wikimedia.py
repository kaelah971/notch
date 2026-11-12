import json
import unittest
from datetime import date

from services.oracle.wikimedia import (
    fetch_range,
    observation_hash,
    resolve_article_identity,
)
from services.trend_radar.http import FetchError
from services.oracle.tests.helpers import (
    FIXTURES,
    FIXED_NOW,
    RaisingFetcher,
    StaticJsonFetcher,
    fixture_fetcher,
)


def payload(*items, article="Bitcoin", project="en.wikipedia", access="all-access", agent="user"):
    return {
        "items": [
            {
                "project": project,
                "article": article,
                "granularity": "daily",
                "timestamp": timestamp,
                "access": access,
                "agent": agent,
                "views": views,
            }
            for timestamp, views in items
        ]
    }


class WikimediaTests(unittest.TestCase):
    def test_complete_fixture_range(self):
        result = fetch_range(
            fixture_fetcher(),
            article="Bitcoin",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 10),
        )
        self.assertTrue(result.complete)
        self.assertEqual(len(result.observations), 71)
        self.assertEqual(result.missing_dates, [])
        self.assertTrue(result.raw_response_hash)
        self.assertEqual(result.retrieved_at.isoformat(), "2026-11-12T01:40:00+00:00")
        first = result.observations["2026-09-01"]
        self.assertEqual(first.views, 3759)
        self.assertEqual(first.project, "en.wikipedia.org")
        self.assertEqual(first.access, "all-access")
        self.assertEqual(first.agent, "user")
        self.assertEqual(observation_hash(first), first.observation_hash)

    def test_missing_and_duplicate_days_are_detected(self):
        missing = fetch_range(
            StaticJsonFetcher(payload(("2026110100", 100), ("2026110300", 120))),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
        )
        self.assertEqual(missing.missing_dates, ["2026-11-02"])
        self.assertFalse(missing.complete)

        duplicate = fetch_range(
            StaticJsonFetcher(
                payload(("2026110100", 100), ("2026110100", 101), ("2026110200", 110))
            ),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
        )
        self.assertEqual(duplicate.duplicate_dates, ["2026-11-01"])
        self.assertFalse(duplicate.complete)

    def test_invalid_source_records_are_rejected(self):
        wrong_project = fetch_range(
            StaticJsonFetcher(payload(("2026110100", 100), project="de.wikipedia")),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1),
        )
        self.assertIsNotNone(wrong_project.error)
        self.assertIn("unexpected project", wrong_project.error)
        wrong_article = fetch_range(
            StaticJsonFetcher(payload(("2026110100", 100), article="Ethereum")),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1),
        )
        self.assertIsNotNone(wrong_article.error)
        wrong_access = fetch_range(
            StaticJsonFetcher(payload(("2026110100", 100), access="desktop")),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1),
        )
        self.assertIsNotNone(wrong_access.error)

    def test_fetch_error_is_reported_not_fabricated(self):
        result = fetch_range(
            RaisingFetcher(FetchError("offline", url="x", kind="network")),
            article="Bitcoin",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 2),
        )
        self.assertIsNotNone(result.error)
        self.assertEqual(result.observations, {})
        self.assertFalse(result.complete)

    def test_identity_resolution(self):
        fetcher = fixture_fetcher()
        btc = resolve_article_identity(fetcher, "Bitcoin")
        cg = resolve_article_identity(fetcher, "ChatGPT")
        nv = resolve_article_identity(fetcher, "Nvidia")
        self.assertEqual(btc["page_id"], 28249265)
        self.assertEqual(cg["page_id"], 72417803)
        self.assertEqual(nv["page_id"], 39120)

    def test_observation_hash_changes_with_views(self):
        result = fetch_range(
            fixture_fetcher(),
            article="Bitcoin",
            start_date=date(2026, 11, 3),
            end_date=date(2026, 11, 3),
        )
        observation = result.observations["2026-11-03"]
        original = observation.observation_hash
        observation.views += 1
        self.assertNotEqual(observation_hash(observation), original)


if __name__ == "__main__":
    unittest.main()
