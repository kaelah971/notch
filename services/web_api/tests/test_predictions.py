from __future__ import annotations

import unittest

from services.web_api.predictions import accuracy_percent, classify_prediction


CHOICES = ["UP", "DOWN"]


def market(*, status: str, winner: int | None = None, resolution_kind: str | None = None):
    return {
        "status": status,
        "choices": CHOICES,
        "winning_outcome": winner,
        "resolution_kind": resolution_kind,
    }


def position(*stakes: str):
    return {"stakes": list(stakes)}


class PredictionClassificationTests(unittest.TestCase):
    def test_correct_prediction(self):
        result = classify_prediction(market(status="resolved", winner=0, resolution_kind="winning_outcome"), position("1000000", "0"))
        self.assertEqual(result, {"status": "CORRECT", "choice": "UP", "choices": ["UP"]})

    def test_incorrect_prediction(self):
        result = classify_prediction(market(status="resolved", winner=0, resolution_kind="winning_outcome"), position("0", "1000000"))
        self.assertEqual(result["status"], "INCORRECT")
        self.assertEqual(result["choice"], "DOWN")

    def test_pending_open_and_closed_markets(self):
        for status in ("open", "closed"):
            with self.subTest(status=status):
                result = classify_prediction(market(status=status), position("1000000", "0"))
                self.assertEqual(result["status"], "PENDING")

    def test_voided_market_is_excluded_from_accuracy(self):
        result = classify_prediction(market(status="voided", resolution_kind="tie"), position("1000000", "0"))
        self.assertEqual(result["status"], "VOIDED")

    def test_unknown_when_winner_or_position_is_unavailable(self):
        missing_winner = classify_prediction(market(status="resolved", resolution_kind="winning_outcome"), position("1000000", "0"))
        hedged = classify_prediction(market(status="resolved", winner=0, resolution_kind="winning_outcome"), position("1000000", "1000000"))
        malformed = classify_prediction(market(status="resolved", winner=0), {"stakes": ["not-a-number", "0"]})
        self.assertEqual(missing_winner["status"], "UNKNOWN")
        self.assertEqual(hedged["status"], "UNKNOWN")
        self.assertEqual(hedged["choices"], ["UP", "DOWN"])
        self.assertEqual(malformed["status"], "UNKNOWN")

    def test_repeated_entries_on_one_side_remain_one_market_prediction(self):
        result = classify_prediction(market(status="resolved", winner=1, resolution_kind="winning_outcome"), position("2000000", "0"))
        self.assertEqual(result["status"], "INCORRECT")
        self.assertEqual(result["choices"], ["UP"])

    def test_accuracy_uses_only_correct_and_incorrect(self):
        self.assertAlmostEqual(accuracy_percent(2, 1), 200 / 3)
        self.assertIsNone(accuracy_percent(0, 0))
        self.assertIsNone(accuracy_percent(0, 0))


if __name__ == "__main__":
    unittest.main()
