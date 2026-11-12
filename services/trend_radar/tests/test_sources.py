import unittest
from datetime import date

from services.trend_radar.models import SourceStatus
from services.trend_radar.sources.coingecko import CoinGeckoAdapter
from services.trend_radar.sources.hackernews import HackerNewsAdapter
from services.trend_radar.sources.wikimedia import WikimediaAdapter, is_topic_article
from services.trend_radar.tests.helpers import (
    FIXED_NOW,
    FailingFetcher,
    StaticFetcher,
    fixture_fetcher,
)

SCAN_DATE = date(2026, 11, 11)


class WikimediaAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = WikimediaAdapter(fixture_fetcher())

    def test_top_articles_filter_and_identity(self):
        result = self.adapter.fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(result.health.status, SourceStatus.OK)
        self.assertEqual(result.health.item_count, 3)
        titles = [observation.title for observation in result.observations]
        self.assertEqual(titles, ["Nvidia", "ChatGPT", "Artificial intelligence"])
        self.assertNotIn("Main Page", titles)
        self.assertNotIn("Special:Search", titles)
        self.assertNotIn("Deaths in 2026", titles)
        self.assertNotIn("List of highest-grossing Indian films", titles)
        self.assertEqual(result.context["reporting_date"], "2026-11-10")
        nvidia = next(o for o in result.observations if o.title == "Nvidia")
        self.assertEqual(nvidia.metrics["rank"], 17)
        self.assertEqual(nvidia.metrics["views"], 123851)
        self.assertEqual(nvidia.source_identity["page_id"], 39120)
        self.assertIn("en.wikipedia.org/wiki/Nvidia", nvidia.url)

    def test_topic_filter(self):
        self.assertFalse(is_topic_article("Main_Page"))
        self.assertFalse(is_topic_article("Special:Search"))
        self.assertFalse(is_topic_article("Wikipedia:Featured_pictures"))
        self.assertFalse(is_topic_article("List_of_highest-grossing_Indian_films"))
        self.assertFalse(is_topic_article("Deaths_in_2026"))
        self.assertTrue(is_topic_article("Nvidia"))
        self.assertTrue(is_topic_article("Ramayana:_Part_1"))

    def test_pageviews_probe_ok_and_missing(self):
        coverage = self.adapter.probe_pageviews(
            article="Nvidia",
            page_id=39120,
            end_date=date(2026, 11, 10),
            days=7,
        )
        self.assertEqual(coverage.status, "ok")
        self.assertEqual(len(coverage.daily_views), 7)
        self.assertGreaterEqual(coverage.min_views, 1000)
        self.assertTrue(coverage.measurable)
        missing = self.adapter.probe_pageviews(
            article="Ethereum",
            page_id=41754003,
            end_date=date(2026, 11, 10),
            days=7,
        )
        self.assertEqual(missing.status, "not_found")
        self.assertFalse(missing.measurable)

    def test_redirect_identity_resolution(self):
        response = {
            "batchcomplete": True,
            "query": {
                "normalized": [{"from": "AI", "to": "Artificial intelligence"}],
                "redirects": [{"from": "AI", "to": "Artificial intelligence"}],
                "pages": [
                        {"pageid": 1164, "ns": 0, "title": "Artificial intelligence"}
                ],
            },
        }
        fetcher = StaticFetcher({"wikipedia.org/w/api.php": response})
        adapter = WikimediaAdapter(fetcher)
        identity, error = adapter.resolve_articles(["AI"])
        self.assertIsNone(error)
        self.assertEqual(identity["AI"]["title"], "Artificial intelligence")
        self.assertEqual(identity["AI"]["page_id"], 1164)


class CoinGeckoAdapterTests(unittest.TestCase):
    def test_trending_coins_and_categories(self):
        result = CoinGeckoAdapter(fixture_fetcher()).fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(result.health.status, SourceStatus.OK)
        self.assertEqual(result.health.item_count, 3)
        ids = [observation.source_identity["coin_id"] for observation in result.observations]
        self.assertEqual(ids, ["bitcoin", "zcash", "solana"])
        bitcoin = next(o for o in result.observations if o.title == "Bitcoin")
        self.assertEqual(bitcoin.source_identity["symbol"], "BTC")
        self.assertEqual(bitcoin.metrics["trending_rank"], 1)
        self.assertIn("https://www.coingecko.com/en/coins/bitcoin", bitcoin.url)
        self.assertEqual(len(result.context["categories"]), 6)
        self.assertIn("not social attention", result.context["note"])

    def test_invalid_records_are_skipped(self):
        payload = {
            "coins": [
                {"item": {}},
                {"item": {"id": "valid", "name": "Valid Coin", "symbol": "VAL"}},
            ],
            "categories": [],
        }
        adapter = CoinGeckoAdapter(StaticFetcher({"api.coingecko.com": payload}))
        result = adapter.fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].source_id, "coingecko:coin:valid")

    def test_failure_is_isolated_and_flagged(self):
        adapter = CoinGeckoAdapter(FailingFetcher({"coingecko"}))
        result = adapter.fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(result.health.status, SourceStatus.FAILED)
        self.assertTrue(result.health.rate_limited)
        self.assertEqual(result.observations, [])


class HackerNewsAdapterTests(unittest.TestCase):
    def test_front_page_stories(self):
        result = HackerNewsAdapter(fixture_fetcher()).fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(result.health.status, SourceStatus.OK)
        self.assertEqual(result.health.item_count, 4)
        nvidia = next(o for o in result.observations if "Nvidia" in o.title)
        self.assertEqual(nvidia.source_id, "hn:story:50459703")
        self.assertEqual(nvidia.metrics["points"], 300)
        self.assertEqual(nvidia.metrics["comments"], 285)
        self.assertIn("news.ycombinator.com/item?id=50459703", nvidia.source_identity["hn_url"])
        self.assertIn("max_story_age_seconds", result.context)

    def test_ask_show_and_invalid_records_are_filtered(self):
        payload = {
            "hits": [
                {"objectID": "1", "title": "Ask HN: What now?", "points": 10},
                {"objectID": "2", "title": "Show HN: My project", "points": 10},
                {"objectID": "3", "title": "", "points": 10},
                {"objectID": None, "title": "No id", "points": 10},
                {"objectID": "4", "title": "A real story", "points": 10, "num_comments": 2},
            ]
        }
        adapter = HackerNewsAdapter(StaticFetcher({"hn.algolia.com": payload}))
        result = adapter.fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].source_id, "hn:story:4")

    def test_failure_is_isolated(self):
        adapter = HackerNewsAdapter(FailingFetcher({"hackernews"}))
        result = adapter.fetch(FIXED_NOW, SCAN_DATE)
        self.assertEqual(result.health.status, SourceStatus.FAILED)
        self.assertEqual(result.observations, [])


if __name__ == "__main__":
    unittest.main()
