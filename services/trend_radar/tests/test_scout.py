"""Deterministic Scout V1 tests over stored Wikimedia observations."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.trend_radar.scout import (
    MIN_SAMPLE_DAYS,
    NOTABLE_CHANGE_BPS,
    build_scout_candidate,
    build_scout_feed,
    pageviews_api_url,
    scout_metadata,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def candidate(
    *,
    title="Nvidia",
    candidate_id="cand_nvidia",
    rows=None,
    observed_at="2026-11-10T23:59:59Z",
    status="ok",
    window_start="2026-11-04",
    window_end="2026-11-10",
):
    rows = rows or [
        {"date": "2026-11-04", "views": 4112},
        {"date": "2026-11-05", "views": 4743},
        {"date": "2026-11-06", "views": 4626},
        {"date": "2026-11-07", "views": 5535},
        {"date": "2026-11-08", "views": 17886},
        {"date": "2026-11-09", "views": 142333},
        {"date": "2026-11-10", "views": 123851},
    ]
    return {
        "candidate_id": candidate_id,
        "canonical_topic_id": "entity:nvidia" if title == "Nvidia" else f"wiki:{title.lower()}",
        "title": title,
        "observed_at": observed_at,
        "source_urls": [f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"],
        "discovery_signals": {"settlement_article": title},
        "settlement_coverage": {
            "article": title,
            "status": status,
            "window_start": window_start,
            "window_end": window_end,
            "daily_views": rows,
            "raw_hashes": ["sha256:fixture-pageviews"],
        },
    }


class ScoutTests(unittest.TestCase):
    def test_real_fixture_movement_is_ranked_and_proposed_for_review(self):
        item = build_scout_candidate(candidate(), now=NOW)
        assert item is not None
        self.assertEqual(item["direction"], "RISING")
        self.assertTrue(item["is_notable"])
        self.assertTrue(item["is_unusual"])
        self.assertEqual(item["candidate_status"], "REVIEWABLE")
        self.assertEqual(item["observation_window"]["sample_count"], 7)
        self.assertEqual(item["change"]["change_bps"], ((123851 - 4112) * 10000) // 4112)
        self.assertTrue(item["evidence_digest"].startswith("sha256:"))
        self.assertEqual(item["proposal"]["status"], "REVIEW_ONLY")
        self.assertTrue(item["proposal"]["human_review_required"])
        self.assertFalse(item["proposal"]["published"])
        self.assertEqual(item["source"]["id"], "wikimedia-pageviews-v1")
        self.assertEqual(item["source"]["api_url"], pageviews_api_url("Nvidia", "2026-11-04", "2026-11-10"))

    def test_threshold_boundary_is_falling_at_negative_two_thousand_bps(self):
        rows = [{"date": f"2026-11-{day:02d}", "views": value} for day, value in zip(range(4, 9), [1000, 1000, 1000, 1000, 800])]
        item = build_scout_candidate(candidate(rows=rows, window_end="2026-11-08"), now=NOW)
        assert item is not None
        self.assertEqual(item["change"]["change_bps"], -NOTABLE_CHANGE_BPS)
        self.assertEqual(item["direction"], "FALLING")

    def test_missing_days_zero_baseline_and_stale_data_stay_honest(self):
        missing = candidate(
            rows=[
                {"date": "2026-11-04", "views": 1000},
                {"date": "2026-11-05", "views": 1200},
                {"date": "2026-11-07", "views": 1500},
                {"date": "2026-11-08", "views": 1600},
                {"date": "2026-11-10", "views": 1800},
            ]
        )
        item = build_scout_candidate(missing, now=NOW)
        assert item is not None
        self.assertEqual(item["candidate_status"], "NEEDS_REVIEW")
        self.assertEqual(item["change"]["change_bps"], 8000)
        self.assertIn("2026-11-06", item["observation_window"]["missing_days"])
        self.assertTrue(any("imputed" in note for note in item["uncertainty"]))

        zero = build_scout_candidate(
            candidate(rows=[{"date": f"2026-11-{day:02d}", "views": 0} for day in range(4, 9)], window_end="2026-11-08"),
            now=NOW,
        )
        assert zero is not None
        self.assertIsNone(zero["change"]["change_bps"])
        self.assertEqual(zero["candidate_status"], "NEEDS_REVIEW")

        stale = build_scout_candidate(candidate(observed_at="2026-11-01T00:00:00Z"), now=NOW)
        assert stale is not None
        self.assertEqual(stale["candidate_status"], "STALE")
        self.assertIsNone(stale["proposal"])

    def test_deduplicates_supported_topics_and_marks_existing_market(self):
        duplicate = candidate(candidate_id="cand_nvidia_duplicate")
        matches = {"nvidia": {"market_id": "market-nvidia", "status": "APPROVED", "topics": ["Nvidia"]}}
        feed = build_scout_feed([candidate(), duplicate], now=NOW, existing_market_matches=matches)
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["candidate_id"], "cand_nvidia")
        self.assertEqual(feed[0]["existing_market_match"]["market_id"], "market-nvidia")
        self.assertIsNone(feed[0]["proposal"])

    def test_direction_filter_and_metadata_are_bounded(self):
        falling_rows = [{"date": f"2026-11-{day:02d}", "views": value} for day, value in zip(range(4, 9), [1000, 900, 850, 800, 700])]
        feed = build_scout_feed([candidate(), candidate(title="Bitcoin", candidate_id="cand_bitcoin", rows=falling_rows, window_end="2026-11-08")], now=NOW, direction="falling", limit=99)
        self.assertEqual([item["topic"] for item in feed], ["Bitcoin"])
        self.assertEqual(scout_metadata()["minimum_sample_days"], MIN_SAMPLE_DAYS)
        self.assertEqual(scout_metadata()["source"], "wikimedia-pageviews-v1")

    def test_malformed_daily_rows_are_ignored_without_fabricating_values(self):
        rows = [
            {"date": "2026-11-04", "views": "not-a-number"},
            {"date": "2026-11-05", "views": -2},
            {"date": "2026-11-06", "views": 1000},
            {"date": "2026-11-07", "views": 1100},
            {"date": "2026-11-08", "views": 1200},
            {"date": "2026-11-09", "views": 1300},
            {"date": "2026-11-10", "views": 1400},
            "invalid-row",
        ]
        item = build_scout_candidate(candidate(rows=rows), now=NOW)
        assert item is not None
        self.assertEqual(item["observation_window"]["sample_count"], 5)
        self.assertEqual(item["baseline"], {"date": "2026-11-06", "views": 1000})
        self.assertEqual(item["current"], {"date": "2026-11-10", "views": 1400})
        self.assertEqual(item["change"]["change_bps"], 4000)

    def test_unsupported_topic_is_not_fabricated_into_scout(self):
        self.assertIsNone(build_scout_candidate(candidate(title="Unknown article"), now=NOW))


if __name__ == "__main__":
    unittest.main()
