import copy
import tempfile
import unittest

from services.oracle.rules import (
    build_contract_args,
    rule_digest,
    validate_create_args,
    validate_rule,
)
from services.oracle.store import FrozenRuleConflict, OracleStore
from services.oracle.tests.helpers import FIXED_NOW, make_service


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.service, cls.store, cls.fetcher = make_service(cls.temp.name)
        cls.demo = cls.service.demo(now=FIXED_NOW)
        cls.by_name = {item["name"]: item for item in cls.demo["rules"]}
        cls.trend_rule = cls.by_name["replay_trend_nvidia"]["rule"]
        cls.battle_rule = cls.by_name["replay_battle_bitcoin_chatgpt"]["rule"]
        cls.future_rule = cls.by_name["future_bitcoin"]["rule"]

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.temp.cleanup()

    def test_rule_hashes_are_canonical_and_not_proposal_ids(self):
        for item in self.demo["rules"]:
            self.assertEqual(item["rule_hash"], rule_digest(item["rule"]))
            self.assertRegex(item["rule_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertFalse(item["rule_hash"].startswith("prop_"))
            self.assertTrue(item["rule"]["candidate"]["source_proposal_refs"])
        hashes = {item["rule_hash"] for item in self.demo["rules"]}
        self.assertEqual(len(hashes), 3)

    def test_trend_rule_contract_args(self):
        args = build_contract_args(self.trend_rule)["args"]
        self.assertEqual(args["mode"], "trend_trading")
        self.assertEqual(args["choices"], ["UP", "DOWN"])
        self.assertNotIn("battle", args)
        self.assertEqual(args["rule_hash"], rule_digest(self.trend_rule))
        self.assertEqual(args["source_id"], "wikimedia-pageviews-v1")
        self.assertEqual(args["invalidation_policy"], "refund_on_void")
        self.assertLess(int(args["open_at"]), int(args["close_at"]))
        self.assertLessEqual(int(args["close_at"]), int(args["resolve_after"]))
        self.assertEqual(validate_create_args({"args": args}), [])

    def test_battle_rule_contract_args(self):
        args = build_contract_args(self.battle_rule)["args"]
        self.assertEqual(args["mode"], "trend_battle")
        battle = args["battle"]
        self.assertEqual(battle["formula"], "growth_comparison_v1")
        self.assertEqual(battle["tie_policy"], "void")
        self.assertEqual(battle["tie_tolerance_bps"], 930)
        self.assertNotEqual(
            battle["topic_a"]["article_title"], battle["topic_b"]["article_title"]
        )
        self.assertEqual(
            battle["topic_a"]["source_id"], args["source_id"]
        )
        self.assertLess(
            int(battle["observation_start"]), int(battle["observation_end"])
        )
        self.assertLessEqual(
            int(battle["observation_end"]), int(args["resolve_after"])
        )
        self.assertEqual(validate_create_args({"args": args}), [])

        bad = copy.deepcopy({"args": args})
        bad["args"]["battle"]["topic_a"]["source_id"] = "other-source"
        self.assertIn("battle_topic_a_source_mismatch", validate_create_args(bad))

    def test_replay_and_future_labels_are_enforced(self):
        mislabeled = copy.deepcopy(self.trend_rule)
        mislabeled["observation"]["replay"] = False
        self.assertIn("future_question_must_be_labeled", validate_rule(mislabeled))

        missing_label = copy.deepcopy(self.trend_rule)
        missing_label["observation"]["replay_label"] = None
        self.assertIn("invalid_replay_label", validate_rule(missing_label))

        future_mislabeled = copy.deepcopy(self.future_rule)
        future_mislabeled["observation"]["replay"] = True
        future_mislabeled["observation"]["replay_label"] = None
        self.assertIn("invalid_replay_label", validate_rule(future_mislabeled))

    def test_invalid_rule_fields_are_rejected(self):
        cases = []
        rule = copy.deepcopy(self.trend_rule)
        rule["formula"]["threshold_bps"] = 1_000_001
        cases.append((rule, "invalid_threshold"))
        rule = copy.deepcopy(self.battle_rule)
        rule["formula"]["tie_tolerance_bps"] = 10001
        cases.append((rule, "invalid_tie_tolerance"))
        rule = copy.deepcopy(self.trend_rule)
        rule["market_timing"]["close_at_ns"] = rule["market_timing"]["open_at_ns"]
        cases.append((rule, "invalid_market_timing"))
        rule = copy.deepcopy(self.trend_rule)
        rule["market_id"] = "bad market id"
        cases.append((rule, "invalid_market_id"))
        rule = copy.deepcopy(self.trend_rule)
        rule["governance"]["auto_approved"] = True
        cases.append((rule, "auto_approval_forbidden"))
        for candidate_rule, expected in cases:
            self.assertIn(expected, validate_rule(candidate_rule))

    def test_duplicate_and_conflicting_rules(self):
        store = OracleStore(":memory:")
        try:
            first = store.freeze_rule(self.trend_rule, now=FIXED_NOW)
            again = store.freeze_rule(self.trend_rule, now=FIXED_NOW)
            self.assertEqual(first["rule_hash"], again["rule_hash"])
            changed = copy.deepcopy(self.trend_rule)
            changed["formula"]["threshold_bps"] += 50
            with self.assertRaises(FrozenRuleConflict):
                store.freeze_rule(changed, now=FIXED_NOW)
            approved = store.approve_rule(
                first["rule_hash"], operator="op", reason="approved for test", now=FIXED_NOW
            )
            self.assertEqual(approved["status"], "APPROVED")
            with self.assertRaises(FrozenRuleConflict):
                store.freeze_rule(changed, now=FIXED_NOW)
            self.assertEqual(
                store.get_rule(first["rule_hash"])["rule"], self.trend_rule
            )
        finally:
            store.close()

    def test_rule_hash_changes_with_threshold(self):
        changed = copy.deepcopy(self.trend_rule)
        changed["formula"]["threshold_bps"] += 50
        self.assertNotEqual(rule_digest(self.trend_rule), rule_digest(changed))
        self.assertEqual(rule_digest(self.trend_rule), rule_digest(copy.deepcopy(self.trend_rule)))

    def test_contract_arg_mutations_are_detected(self):
        args = build_contract_args(self.trend_rule)["args"]
        for mutation, expected in [
            ("rule_hash", "invalid_rule_hash"),
            ("open_at", "invalid_timing"),
            ("mode", "invalid_mode"),
        ]:
            bad = copy.deepcopy({"args": args})
            if mutation == "rule_hash":
                bad["args"][mutation] = "sha256:bad"
            elif mutation == "open_at":
                bad["args"][mutation] = bad["args"]["close_at"]
            else:
                bad["args"][mutation] = "unknown"
            self.assertIn(expected, validate_create_args(bad))


if __name__ == "__main__":
    unittest.main()
