import json
import tempfile
import unittest

from services.oracle.rules import validate_create_args, validate_rule
from services.oracle.tests.helpers import FIXED_NOW, make_service


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.service, cls.store, cls.fetcher = make_service(cls.temp.name)
        cls.demo = cls.service.demo(now=FIXED_NOW)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.temp.cleanup()

    def test_demo_has_three_draft_rules_and_no_onchain_action(self):
        self.assertEqual(self.demo["onchain_actions"], "none")
        self.assertEqual(len(self.demo["rules"]), 3)
        names = {item["name"] for item in self.demo["rules"]}
        self.assertEqual(
            names,
            {"future_bitcoin", "replay_trend_nvidia", "replay_battle_bitcoin_chatgpt"},
        )
        for item in self.demo["rules"]:
            self.assertEqual(item["status"], "DRAFT")
            self.assertTrue(item["rule"]["governance"]["operator_approval_required"])
            self.assertFalse(item["rule"]["governance"]["auto_approved"])
            self.assertEqual(validate_rule(item["rule"]), [])
            self.assertEqual(validate_create_args(item["contract_args"]), [])
            self.assertRegex(item["rule_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_replay_and_future_are_labeled_and_evidence_is_verified(self):
        by_name = {item["name"]: item for item in self.demo["rules"]}
        future = by_name["future_bitcoin"]
        trend = by_name["replay_trend_nvidia"]
        battle = by_name["replay_battle_bitcoin_chatgpt"]

        self.assertFalse(future["rule"]["observation"]["replay"])
        self.assertTrue(future["rule"]["question"].startswith("FORECAST"))
        self.assertIsNone(future["evidence"])
        self.assertTrue(future["evidence_pending"])

        for item, expected_outcome in [(trend, "UP"), (battle, "TOPIC_A")]:
            self.assertTrue(item["rule"]["observation"]["replay"])
            self.assertEqual(
                item["rule"]["observation"]["replay_label"], "HISTORICAL_REPLAY"
            )
            self.assertTrue(item["rule"]["question"].startswith("HISTORICAL REPLAY"))
            self.assertEqual(item["evidence"]["evidence"]["outcome"], expected_outcome)
            self.assertTrue(item["evidence"]["verification"]["valid"])
            self.assertTrue(item["evidence"]["evidence"]["evidence_digest"].startswith("sha256:"))
            self.assertEqual(item["resolution_plan_preview"]["status"], "BLOCKED")
            self.assertIn(
                "ONCHAIN_MARKET_NOT_PROVIDED",
                item["resolution_plan_preview"]["blockers"],
            )
            self.assertIn(
                "RULE_NOT_APPROVED", item["resolution_plan_preview"]["blockers"]
            )

    def test_calibration_and_reviews(self):
        calibrations = {item["name"]: item for item in self.demo["calibrations"]}
        self.assertEqual(calibrations["future_bitcoin"]["suggested_threshold_bps"], 2300)
        self.assertEqual(calibrations["replay_trend_nvidia"]["suggested_threshold_bps"], 1350)
        self.assertEqual(
            calibrations["replay_battle_bitcoin_chatgpt"]["suggested_tie_tolerance_bps"],
            930,
        )
        for item in self.demo["calibrations"]:
            self.assertTrue(item["report_digest"].startswith("sha256:"))
        self.assertEqual(self.demo["battle_pair"]["recommendation"], "READY_FOR_OPERATOR_REVIEW")
        self.assertEqual(
            self.demo["correlation_example"]["recommendation"],
            "REJECT_CORRELATED_TOPICS",
        )
        for review in self.demo["reviews"]:
            self.assertTrue(review["operator_approval_required"])
            self.assertNotEqual(review["recommendation"], "APPROVED")

    def test_source_ranges_are_complete_and_store_is_consistent(self):
        for article, range_info in self.demo["source_ranges"].items():
            self.assertEqual(range_info["observations"], 71)
            self.assertEqual(range_info["missing_dates"], [])
            self.assertTrue(range_info["raw_response_hash"])
        self.assertEqual(len(self.store.list_evidence()), 2)
        self.assertEqual(len(self.store.list_calibrations()), 5)
        self.assertEqual(len(self.store.list_rules()), 3)
        self.assertEqual([r["status"] for r in self.store.list_rules()], ["DRAFT"] * 3)
        demo_file = __import__("pathlib").Path(self.temp.name) / "demo.json"
        self.assertTrue(demo_file.exists())
        self.assertEqual(json.loads(demo_file.read_text(encoding="utf-8"))["rules"][0]["status"], "DRAFT")


if __name__ == "__main__":
    unittest.main()
