import unittest
from datetime import datetime, timezone

from services.trend_radar.eligibility import (
    battle_compatible,
    evaluate_candidates,
    measurement_signature,
)
from services.trend_radar.models import Category, EligibilityStatus
from services.trend_radar.tests.helpers import (
    FIXED_NOW,
    make_candidate,
    make_coverage,
    make_health,
)

HEALTH = {
    "wikimedia": make_health("wikimedia"),
    "coingecko": make_health("coingecko"),
    "hackernews": make_health("hackernews"),
}


def evaluate(candidate, coverage=None, probed=True, health=None):
    coverage_map = {}
    probed_ids = set()
    if coverage is not None:
        coverage_map[candidate.candidate_id] = coverage
    if probed:
        probed_ids.add(candidate.candidate_id)
    return evaluate_candidates(
        [candidate],
        health_by_source=health or HEALTH,
        coverage_by_candidate=coverage_map,
        probed_ids=probed_ids,
        now=FIXED_NOW,
    )[0]


class EligibilityTests(unittest.TestCase):
    def test_eligible_with_complete_coverage(self):
        candidate = make_candidate(category=Category.AI)
        result = evaluate(candidate, make_coverage(min_views=5000))
        self.assertEqual(result.eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertEqual(result.proposed_market_modes, ["trend_trading"])
        self.assertIn("eligible_settlement_coverage", result.eligibility_reasons)

    def test_no_wikimedia_coverage_is_not_measurable(self):
        candidate = make_candidate(
            sources=("hackernews",), settlement_article=None, category=Category.AI
        )
        result = evaluate(candidate)
        self.assertEqual(result.eligibility_status, EligibilityStatus.NOT_MEASURABLE)
        self.assertIn("no_settlement_coverage", result.eligibility_reasons)
        self.assertEqual(result.proposed_market_modes, [])

    def test_not_probed_is_needs_review(self):
        candidate = make_candidate()
        result = evaluate(candidate, probed=False)
        self.assertEqual(result.eligibility_status, EligibilityStatus.NEEDS_REVIEW)
        self.assertIn("coverage_probe_not_run", result.eligibility_reasons)

    def test_not_found_coverage_is_not_measurable(self):
        candidate = make_candidate()
        result = evaluate(candidate, make_coverage(status="not_found", min_views=None, days=0))
        self.assertEqual(result.eligibility_status, EligibilityStatus.NOT_MEASURABLE)
        self.assertIn("wikimedia_pageviews_not_found", result.eligibility_reasons)

    def test_probe_error_is_needs_review(self):
        candidate = make_candidate()
        result = evaluate(candidate, make_coverage(status="error", min_views=None, days=0))
        self.assertEqual(result.eligibility_status, EligibilityStatus.NEEDS_REVIEW)
        self.assertIn("coverage_probe_failed", result.eligibility_reasons)

    def test_incomplete_history_is_needs_review(self):
        candidate = make_candidate()
        result = evaluate(candidate, make_coverage(status="incomplete", min_views=5000, days=3))
        self.assertEqual(result.eligibility_status, EligibilityStatus.NEEDS_REVIEW)
        self.assertIn("incomplete_history", result.eligibility_reasons)

    def test_low_baseline_is_needs_review(self):
        candidate = make_candidate()
        result = evaluate(candidate, make_coverage(status="insufficient_baseline", min_views=500))
        self.assertEqual(result.eligibility_status, EligibilityStatus.NEEDS_REVIEW)
        self.assertIn("baseline_below_minimum", result.eligibility_reasons)

    def test_stale_observation_is_stale(self):
        candidate = make_candidate(
            observed_at=datetime(2026, 10, 1, tzinfo=timezone.utc)
        )
        result = evaluate(candidate, make_coverage())
        self.assertEqual(result.eligibility_status, EligibilityStatus.STALE)
        self.assertIn("stale_observation", result.eligibility_reasons)

    def test_stale_source_is_stale(self):
        candidate = make_candidate()
        result = evaluate(
            candidate,
            make_coverage(),
            health={"wikimedia": make_health("wikimedia", stale=True)},
        )
        self.assertEqual(result.eligibility_status, EligibilityStatus.STALE)
        self.assertIn("stale_source", result.eligibility_reasons)

    def test_ambiguous_topic_needs_review(self):
        candidate = make_candidate(ambiguous=True)
        result = evaluate(candidate, make_coverage())
        self.assertEqual(result.eligibility_status, EligibilityStatus.NEEDS_REVIEW)
        self.assertIn("ambiguous_topic", result.eligibility_reasons)

    def test_invalid_source_record_is_rejected(self):
        candidate = make_candidate(title="", source_identities=[])
        result = evaluate(candidate)
        self.assertEqual(result.eligibility_status, EligibilityStatus.REJECTED)
        self.assertIn("invalid_source_record", result.eligibility_reasons)

    def test_battle_compatibility_requires_same_measurement(self):
        a = make_candidate(candidate_id="cand_a", title="Topic A", settlement_article="Topic A")
        b = make_candidate(candidate_id="cand_b", title="Topic B", settlement_article="Topic B")
        a.eligibility_status = EligibilityStatus.ELIGIBLE
        b.eligibility_status = EligibilityStatus.ELIGIBLE
        self.assertTrue(battle_compatible(a, b))
        self.assertEqual(measurement_signature(a), measurement_signature(b))

        b.discovery_signals["measurement_signature"] = {
            "source": "wikimedia-pageviews-v1",
            "project": "de.wikipedia.org",
            "access": "all-access",
            "agent": "user",
            "metric": "daily_pageviews",
        }
        self.assertFalse(battle_compatible(a, b))

    def test_incompatible_candidate_is_not_battle_compatible(self):
        a = make_candidate(candidate_id="cand_a", title="Topic A", settlement_article="Topic A")
        b = make_candidate(candidate_id="cand_b", title="Topic B", settlement_article="Topic B")
        a.eligibility_status = EligibilityStatus.ELIGIBLE
        b.eligibility_status = EligibilityStatus.NEEDS_REVIEW
        self.assertFalse(battle_compatible(a, b))

    def test_same_article_is_not_battle_compatible(self):
        a = make_candidate(candidate_id="cand_a", title="Topic A", settlement_article="Topic A")
        b = make_candidate(candidate_id="cand_b", title="Topic A again", settlement_article="Topic A")
        a.eligibility_status = EligibilityStatus.ELIGIBLE
        b.eligibility_status = EligibilityStatus.ELIGIBLE
        self.assertFalse(battle_compatible(a, b))


if __name__ == "__main__":
    unittest.main()
