import copy
import dataclasses
import unittest
from datetime import date

from services.oracle.calibration import calibrate_battle, calibrate_trend
from services.oracle.tests.helpers import fixture_fetcher
from services.oracle.wikimedia import fetch_range

START = date(2026, 9, 1)
END = date(2026, 11, 10)
BASELINE = date(2026, 11, 3)
TARGET = date(2026, 11, 10)
CAL_END = date(2026, 11, 2)


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fetcher = fixture_fetcher()
        cls.ranges = {
            article: fetch_range(
                fetcher, article=article, start_date=START, end_date=END
            )
            for article in ("Bitcoin", "ChatGPT", "Nvidia")
        }

    def test_trend_calibration_from_real_fixture(self):
        nv = calibrate_trend(
            self.ranges["Nvidia"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(nv.status, "OK")
        self.assertEqual(nv.observation_status, "AVAILABLE")
        self.assertEqual(nv.baseline_views, 4743)
        self.assertEqual(nv.target_views, 123851)
        self.assertEqual(nv.suggested_threshold_bps, 1350)
        self.assertEqual(nv.weekly_growth_stats["count"], 56)
        self.assertTrue(nv.report_digest.startswith("sha256:"))
        self.assertEqual(len(nv.source_raw_hashes), 1)
        self.assertEqual(nv.reasons, [])

        btc = calibrate_trend(
            self.ranges["Bitcoin"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(btc.status, "OK")
        self.assertEqual(btc.suggested_threshold_bps, 2350)

    def test_calibration_digest_is_reproducible(self):
        first = calibrate_trend(
            self.ranges["Nvidia"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        second = calibrate_trend(
            self.ranges["Nvidia"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(first.report_digest, second.report_digest)
        self.assertEqual(first.weekly_growth_bps, second.weekly_growth_bps)

    def test_battle_calibration(self):
        report = calibrate_battle(
            self.ranges["Bitcoin"],
            self.ranges["ChatGPT"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.growth_a_bps, 1620)
        self.assertEqual(report.growth_b_bps, -4931)
        self.assertEqual(report.difference_bps, 6551)
        self.assertEqual(report.suggested_tie_tolerance_bps, 930)
        self.assertEqual(report.tie_policy, "void")
        self.assertEqual(report.abs_difference_stats["count"], 56)

    def test_missing_day_holds(self):
        broken = copy.deepcopy(self.ranges["Nvidia"])
        removed = "2026-10-01"
        broken.observations.pop(removed)
        broken.missing_dates.append(removed)
        report = calibrate_trend(
            broken,
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(report.status, "HOLD")
        self.assertIn("missing_source_observations", report.reasons)

    def test_low_baseline_holds(self):
        broken = copy.deepcopy(self.ranges["Nvidia"])
        day = broken.observations[BASELINE.isoformat()]
        broken.observations[BASELINE.isoformat()] = dataclasses.replace(day, views=100)
        report = calibrate_trend(
            broken,
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=CAL_END,
            replay=True,
        )
        self.assertEqual(report.status, "HOLD")
        self.assertIn("baseline_below_minimum", report.reasons)

    def test_lookahead_calibration_holds(self):
        report = calibrate_trend(
            self.ranges["Nvidia"],
            baseline_date=BASELINE,
            target_date=TARGET,
            calibration_end=BASELINE,
            replay=True,
        )
        self.assertEqual(report.status, "HOLD")
        self.assertIn("lookahead_calibration_window", report.reasons)

    def test_future_calibration_is_pending_observation(self):
        report = calibrate_trend(
            self.ranges["Bitcoin"],
            baseline_date=date(2026, 11, 16),
            target_date=date(2026, 11, 23),
            calibration_end=date(2026, 11, 10),
            replay=False,
        )
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.observation_status, "PENDING_OBSERVATION")
        self.assertIsNone(report.baseline_views)
        self.assertIsNone(report.target_views)
        self.assertIsNotNone(report.suggested_threshold_bps)


if __name__ == "__main__":
    unittest.main()
