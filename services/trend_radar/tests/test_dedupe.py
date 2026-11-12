import unittest
from datetime import datetime, timezone

from services.trend_radar.dedupe import build_candidates
from services.trend_radar.models import RawObservation, SourceResult


NOW = datetime(2026, 11, 11, 23, 45, tzinfo=timezone.utc)


def wiki(title, page_id=1, views=10000, rank=10):
    return RawObservation(
        source="wikimedia",
        source_id=f"wikimedia:en.wikipedia.org:{title}",
        title=title,
        url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        observed_at=NOW,
        metrics={"views": views, "rank": rank, "reporting_date": "2026-11-10"},
        source_identity={
            "source": "wikimedia",
            "project": "en.wikipedia.org",
            "article_resolved": title,
            "page_id": page_id,
            "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        },
        reporting_date=datetime(2026, 11, 10, tzinfo=timezone.utc).date(),
        raw_hash="wiki-hash",
    )


def coingecko(coin_id, symbol, name, rank=1):
    return RawObservation(
        source="coingecko",
        source_id=f"coingecko:coin:{coin_id}",
        title=name,
        url=f"https://www.coingecko.com/en/coins/{coin_id}",
        observed_at=NOW,
        metrics={"symbol": symbol, "trending_rank": rank, "market_cap_rank": 1},
        source_identity={
            "source": "coingecko",
            "coin_id": coin_id,
            "symbol": symbol,
            "name": name,
            "url": f"https://www.coingecko.com/en/coins/{coin_id}",
        },
        raw_hash="coin-hash",
    )


def hn(story_id, title, points=200):
    return RawObservation(
        source="hackernews",
        source_id=f"hn:story:{story_id}",
        title=title,
        url=f"https://news.ycombinator.com/item?id={story_id}",
        observed_at=NOW,
        metrics={"points": points, "comments": 10},
        source_identity={
            "source": "hackernews",
            "story_id": story_id,
            "title": title,
            "url": f"https://news.ycombinator.com/item?id={story_id}",
        },
        raw_hash="hn-hash",
    )


class DedupeTests(unittest.TestCase):
    def test_bitcoin_btc_and_sources_merge(self):
        candidates = build_candidates(
            [
                SourceResult(
                    source="wikimedia",
                    observations=[wiki("Bitcoin", page_id=28249265, views=16000, rank=100)],
                ),
                SourceResult(
                    source="coingecko",
                    observations=[coingecko("bitcoin", "BTC", "Bitcoin", rank=2)],
                ),
                SourceResult(
                    source="hackernews",
                    observations=[hn("1", "Bitcoin hits a new high", points=500)],
                ),
            ],
            now=NOW,
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.canonical_topic_id, "entity:bitcoin")
        self.assertEqual(candidate.title, "Bitcoin")
        self.assertEqual(candidate.discovery_signals["source_count"], 3)
        self.assertEqual(len(candidate.source_identities), 3)
        self.assertEqual(len(candidate.discovery_evidence), 3)
        self.assertTrue(any(alias.casefold() == "btc" for alias in candidate.aliases))
        self.assertEqual(candidate.discovery_signals["settlement_article"], "Bitcoin")
        self.assertEqual(candidate.discovery_signals["settlement_page_id"], 28249265)

    def test_chatgpt_aliases_merge_but_openai_stays_separate(self):
        candidates = build_candidates(
            [
                SourceResult(source="wikimedia", observations=[wiki("ChatGPT", page_id=72417803)]),
                SourceResult(
                    source="hackernews",
                    observations=[hn("2", "OpenAI ChatGPT gets a new feature")],
                ),
                SourceResult(
                    source="hackernews",
                    observations=[hn("3", "OpenAI valuation report")],
                ),
            ],
            now=NOW,
        )
        by_key = {candidate.canonical_topic_id: candidate for candidate in candidates}
        self.assertIn("entity:chatgpt", by_key)
        self.assertIn("entity:openai", by_key)
        chatgpt = by_key["entity:chatgpt"]
        self.assertEqual(chatgpt.discovery_signals["source_count"], 2)
        self.assertTrue(any("ChatGPT" in alias for alias in chatgpt.aliases))

    def test_similar_names_are_not_merged(self):
        candidates = build_candidates(
            [
                SourceResult(
                    source="hackernews",
                    observations=[
                        hn("10", "Apple event announced"),
                        hn("11", "Apple Inc. earnings"),
                    ],
                )
            ],
            now=NOW,
        )
        self.assertEqual(len(candidates), 2)
        self.assertNotEqual(candidates[0].canonical_topic_id, candidates[1].canonical_topic_id)
        for candidate in candidates:
            self.assertIsNone(candidate.discovery_signals["settlement_article"])

    def test_same_hn_story_title_deduplicates_and_preserves_ids(self):
        candidates = build_candidates(
            [
                SourceResult(
                    source="hackernews",
                    observations=[
                        hn("20", "A very specific story title"),
                        hn("21", "A very specific story title"),
                    ],
                )
            ],
            now=NOW,
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(len(candidate.discovery_evidence), 2)
        ids = {item["source_id"] for item in candidate.discovery_evidence}
        self.assertEqual(ids, {"hn:story:20", "hn:story:21"})

    def test_source_specific_wiki_topic_is_not_forced_into_an_entity(self):
        candidates = build_candidates(
            [
                SourceResult(
                    source="wikimedia",
                    observations=[wiki("Ramayana: Part 1", page_id=12345, views=800000, rank=2)],
                )
            ],
            now=NOW,
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertTrue(candidate.canonical_topic_id.startswith("wiki:en.wikipedia.org:"))
        self.assertEqual(candidate.discovery_signals["settlement_article"], "Ramayana: Part 1")
        self.assertEqual(candidate.discovery_signals["settlement_source"], "observed_wiki_article")
        self.assertTrue(candidate.canonical_topic_id)


if __name__ == "__main__":
    unittest.main()
