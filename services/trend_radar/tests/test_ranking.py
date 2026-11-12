import random
import unittest
from datetime import datetime, timezone

from services.trend_radar.models import Category, EligibilityStatus
from services.trend_radar.ranking import rank_candidates
from services.trend_radar.tests.helpers import FIXED_NOW, make_candidate, make_coverage, make_health


class RankingTests(unittest.TestCase):
    def health(self, *sources):
        return {source: make_health(source) for source in sources}

    def test_score_components_and_coverage(self):
        candidate = make_candidate(sources=("wikimedia", "hackernews"), category=Category.AI)
        candidate.settlement_coverage = make_coverage(min_views=5000)
        ranked = rank_candidates([candidate], self.health("wikimedia", "hackernews"), FIXED_NOW)
        signals = ranked[0].discovery_signals
        components = signals["score_components"]
        self.assertEqual(components["confirmations"], 10)
        self.assertEqual(components["settlement_coverage"], 25)
        self.assertEqual(components["freshness"], 5)
        self.assertEqual(components["category_relevance"], 5)
        self.assertGreater(signals["score"], 50)

    def test_missing_coverage_gets_no_coverage_points(self):
        candidate = make_candidate(sources=("hackernews",), settlement_article=None)
        ranked = rank_candidates([candidate], self.health("hackernews"), FIXED_NOW)
        self.assertEqual(ranked[0].discovery_signals["score_components"]["settlement_coverage"], 0)
        self.assertEqual(ranked[0].reliability, "low")

    def test_stale_source_removes_freshness_points(self):
        candidate = make_candidate(sources=("wikimedia",))
        health = {"wikimedia": make_health("wikimedia", stale=True)}
        ranked = rank_candidates([candidate], health, FIXED_NOW)
        self.assertEqual(ranked[0].discovery_signals["score_components"]["freshness"], 0)

    def test_ranking_is_deterministic_under_input_shuffle(self):
        candidates = [
            make_candidate(candidate_id=f"cand_{index}", title=f"Topic {index}", sources=("wikimedia",))
            for index in range(8)
        ]
        health = self.health("wikimedia")
        first = [c.candidate_id for c in rank_candidates(candidates, health, FIXED_NOW)]
        shuffled = list(candidates)
        random.Random(7).shuffle(shuffled)
        second = [c.candidate_id for c in rank_candidates(shuffled, health, FIXED_NOW)]
        self.assertEqual(first, second)

    def test_equal_scores_tie_break_by_candidate_id(self):
        a = make_candidate(candidate_id="cand_b", title="Same", sources=("hackernews",))
        b = make_candidate(candidate_id="cand_a", title="Same", sources=("hackernews",))
        ranked = rank_candidates([a, b], self.health("hackernews"), FIXED_NOW)
        self.assertEqual([c.candidate_id for c in ranked], ["cand_a", "cand_b"])

    def test_no_entity_specific_hardcoded_boost(self):
        a = make_candidate(candidate_id="cand_a", title="Nvidia", canonical_topic_id="entity:nvidia")
        b = make_candidate(candidate_id="cand_b", title="Ordinary Topic", canonical_topic_id="test:b")
        ranked = rank_candidates([a, b], self.health("wikimedia"), FIXED_NOW)
        self.assertEqual(
            ranked[0].discovery_signals["score"], ranked[1].discovery_signals["score"]
        )

    def test_recency_degrades(self):
        fresh = make_candidate(observed_at=FIXED_NOW)
        old = make_candidate(observed_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
        ranked = rank_candidates([fresh, old], self.health("wikimedia"), FIXED_NOW)
        self.assertGreater(
            fresh.discovery_signals["score_components"]["recency"],
            old.discovery_signals["score_components"]["recency"],
        )

    def test_hn_prominence_uses_max_story_points(self):
        candidate = make_candidate(
            sources=("hackernews",),
            evidence=[
                {"source": "hackernews", "metrics": {"points": 50}},
                {"source": "hackernews", "metrics": {"points": 500}},
            ],
        )
        ranked = rank_candidates([candidate], self.health("hackernews"), FIXED_NOW)
        signals = ranked[0].discovery_signals
        self.assertEqual(signals["prominence_detail"]["hackernews_points"], 500)
        self.assertEqual(signals["score_components"]["prominence"], 25)


if __name__ == "__main__":
    unittest.main()
