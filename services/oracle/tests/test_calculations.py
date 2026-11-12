import unittest

from services.oracle.calculations import (
    CalculationError,
    battle_outcome,
    growth_bps,
    growth_stats,
    percentile,
    round_up,
    trend_calculation,
    trend_outcome,
    validate_views,
)


class CalculationTests(unittest.TestCase):
    def test_positive_negative_zero_growth(self):
        self.assertEqual(growth_bps(1000, 1150), 1500)
        self.assertEqual(growth_bps(1000, 900), -1000)
        self.assertEqual(growth_bps(1000, 1000), 0)
        self.assertEqual(growth_bps(3, 1), -6667)
        self.assertEqual(growth_bps(3, 4), 3333)

    def test_exact_threshold_is_up(self):
        self.assertEqual(trend_outcome(1500, 1500), "UP")
        self.assertEqual(trend_outcome(1499, 1500), "DOWN")
        self.assertEqual(trend_outcome(0, 0), "UP")
        self.assertEqual(trend_outcome(-1, 0), "DOWN")

    def test_battle_boundaries(self):
        self.assertEqual(battle_outcome(1000, 400, 600), "TIE")
        self.assertEqual(battle_outcome(1000, 400, 599), "TOPIC_A")
        self.assertEqual(battle_outcome(400, 1000, 600), "TIE")
        self.assertEqual(battle_outcome(400, 1000, 599), "TOPIC_B")
        self.assertEqual(battle_outcome(1000, 400, 0), "TOPIC_A")

    def test_low_baseline_is_invalid(self):
        result = trend_calculation(999, 2000, 1500, 1000)
        self.assertEqual(result["outcome"], "INVALID")
        self.assertEqual(result["invalidity_reason"], "baseline_below_minimum")
        exact = trend_calculation(1000, 1150, 1500, 1000)
        self.assertEqual(exact["outcome"], "UP")
        self.assertEqual(exact["growth_bps"], 1500)

    def test_u64_boundaries_do_not_wrap(self):
        self.assertEqual(validate_views("v", 2**64 - 1), 2**64 - 1)
        with self.assertRaises(CalculationError):
            validate_views("v", 2**64)
        with self.assertRaises(CalculationError):
            validate_views("v", -1)
        self.assertEqual(growth_bps(1, 2**64 - 1), (2**64 - 2) * 10000)
        self.assertEqual(growth_bps(2**64 - 1, 2**64 - 1), 0)
        with self.assertRaises(CalculationError):
            growth_bps(0, 1)

    def test_percentile_and_round_up(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(percentile(values, 50), 5)
        self.assertEqual(percentile(values, 75), 8)
        self.assertEqual(percentile(values, 10), 1)
        self.assertIsNone(percentile([], 50))
        self.assertEqual(round_up(924, 10), 930)
        self.assertEqual(round_up(925, 10), 930)
        self.assertEqual(round_up(0, 10), 0)
        self.assertEqual(round_up(-5, 10), 0)
        stats = growth_stats(values)
        self.assertEqual(stats["count"], 10)
        self.assertEqual(stats["p75"], 8)
        self.assertEqual(stats["mean_abs"], 5)


if __name__ == "__main__":
    unittest.main()
