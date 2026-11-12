import copy
import tempfile
import unittest
from datetime import date

from services.oracle.contract import ResolutionConflict
from services.oracle.evidence import build_evidence
from services.oracle.models import ResolutionPlan
from services.oracle.store import OracleStore
from services.oracle.tests.helpers import (
    FIXED_NOW,
    LATER,
    fake_market,
    make_service,
)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_temp = tempfile.TemporaryDirectory()
        cls.class_service, cls.class_store, cls.fetcher = make_service(cls.class_temp.name)
        cls.demo = cls.class_service.demo(now=FIXED_NOW)
        cls.rules = {item["name"]: item for item in cls.demo["rules"]}
        cls.ranges = cls.class_service.load_ranges(
            ["Bitcoin", "ChatGPT", "Nvidia"], date(2026, 9, 1), date(2026, 11, 10)
        )
        cls.class_store.close()

    @classmethod
    def tearDownClass(cls):
        cls.class_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service, self.store, _ = make_service(self.temp.name)
        for item in self.demo["rules"]:
            self.store.freeze_rule(item["rule"], now=FIXED_NOW)
            if item.get("evidence"):
                self.store.save_evidence(item["evidence"]["evidence"], now=FIXED_NOW)
        for name in ("replay_trend_nvidia", "replay_battle_bitcoin_chatgpt"):
            item = self.rules[name]
            self.store.approve_rule(
                item["rule_hash"],
                operator="test-operator",
                reason="test approval",
                now=FIXED_NOW,
            )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_trend_winner_prepared_with_exact_args(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"])
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        self.assertTrue(result["persisted"])
        plan = result["plan"]
        self.assertEqual(plan["status"], "PREPARED")
        self.assertEqual(plan["action"], "resolve_market")
        call = plan["contract_call"]
        self.assertEqual(call["method"], "resolve_market")
        self.assertEqual(
            set(call["args"]), {"market_id", "winning_outcome", "evidence_hash"}
        )
        self.assertEqual(call["args"]["winning_outcome"], 0)
        self.assertEqual(
            call["args"]["evidence_hash"],
            item["evidence"]["evidence"]["evidence_digest"],
        )
        self.assertNotIn("transaction_hash", plan)
        self.assertIn("<resolver-account>", plan["near_cli_command_template"])
        self.assertNotIn("private", plan["near_cli_command_template"].casefold())

    def test_battle_winner_prepared(self):
        item = self.rules["replay_battle_bitcoin_chatgpt"]
        market = fake_market(item["rule"])
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "PREPARED")
        self.assertEqual(plan["action"], "resolve_market")
        self.assertEqual(plan["contract_call"]["args"]["winning_outcome"], 0)

    def test_preparation_is_idempotent(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"])
        first = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        second = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["job_id"], second["job_id"])

    def test_bad_onchain_configuration_is_blocked(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"])
        market["rule_hash"] = "sha256:" + "0" * 64
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        self.assertFalse(result["persisted"])
        plan = result["plan"]
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertIn("RULE_HASH_MISMATCH", plan["blockers"])
        self.assertIsNone(self.store.get_job(plan["job_id"]))

    def test_too_early_is_blocked(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"])
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=FIXED_NOW,
        )
        self.assertFalse(result["persisted"])
        self.assertIn("RESOLVE_TOO_EARLY", result["plan"]["blockers"])

    def test_final_market_has_no_call(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"], status="resolved")
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "ALREADY_FINAL")
        self.assertIsNone(plan["contract_call"])

    def test_no_winning_stake_maps_to_void(self):
        item = self.rules["replay_trend_nvidia"]
        market = fake_market(item["rule"], totals=("0", "1000000"))
        result = self.service.prepare(
            rule_hash=item["rule_hash"],
            evidence_digest=item["evidence"]["evidence"]["evidence_digest"],
            market_view=market,
            now=LATER,
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "PREPARED")
        self.assertEqual(plan["action"], "void_market")
        self.assertEqual(
            set(plan["contract_call"]["args"]), {"market_id", "reason_hash"}
        )
        self.assertTrue(
            any("NO_WINNING_STAKE" in warning for warning in plan["warnings"])
        )

    def test_tie_maps_to_resolve_tie(self):
        tie_rule = copy.deepcopy(
            self.rules["replay_battle_bitcoin_chatgpt"]["rule"]
        )
        tie_rule["market_id"] = "s3b-test-tie"
        tie_rule["formula"]["tie_tolerance_bps"] = 7000
        tie_rule["question"] = (
            "HISTORICAL REPLAY (not a forecast): Bitcoin versus ChatGPT; a difference "
            "within 7000 bps is a tie."
        )
        frozen = self.store.freeze_rule(tie_rule, now=FIXED_NOW)
        self.store.approve_rule(
            frozen["rule_hash"], operator="test", reason="test tie", now=FIXED_NOW
        )
        evidence = build_evidence(tie_rule, self.ranges)
        self.assertEqual(evidence.outcome, "TIE")
        self.store.save_evidence(evidence, now=FIXED_NOW)
        market = fake_market(tie_rule)
        result = self.service.prepare(
            rule_hash=frozen["rule_hash"],
            evidence_digest=evidence.evidence_digest,
            market_view=market,
            now=LATER,
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "PREPARED")
        self.assertEqual(plan["action"], "resolve_tie")
        self.assertEqual(
            set(plan["contract_call"]["args"]), {"market_id", "evidence_hash"}
        )

    def test_invalid_evidence_maps_to_void(self):
        invalid_rule = copy.deepcopy(self.rules["replay_trend_nvidia"]["rule"])
        invalid_rule["market_id"] = "s3b-test-invalid"
        invalid_rule["observation"]["target_date"] = "2026-11-11"
        invalid_rule["question"] = (
            "HISTORICAL REPLAY (not a forecast): missing target observation test."
        )
        frozen = self.store.freeze_rule(invalid_rule, now=FIXED_NOW)
        self.store.approve_rule(
            frozen["rule_hash"],
            operator="test",
            reason="test invalid",
            now=FIXED_NOW,
        )
        evidence = build_evidence(invalid_rule, self.ranges)
        self.assertEqual(evidence.outcome, "INVALID")
        self.store.save_evidence(evidence, now=FIXED_NOW)
        market = fake_market(invalid_rule)
        result = self.service.prepare(
            rule_hash=frozen["rule_hash"],
            evidence_digest=evidence.evidence_digest,
            market_view=market,
            now=LATER,
        )
        plan = result["plan"]
        self.assertEqual(plan["status"], "PREPARED")
        self.assertEqual(plan["action"], "void_market")
        self.assertEqual(plan["outcome"], "INVALID")
        self.assertEqual(
            set(plan["contract_call"]["args"]), {"market_id", "reason_hash"}
        )

    def test_conflicting_jobs_are_rejected(self):
        store = OracleStore(":memory:")
        try:
            base = dict(
                schema_version="notch.oracle.resolution-plan/1",
                market_id="m1",
                rule_hash="sha256:" + "1" * 64,
                mode="trend_trading",
                outcome="UP",
                action="resolve_market",
                status="PREPARED",
                contract_call={"method": "resolve_market", "args": {}},
                near_cli_command_template=None,
                blockers=[],
                warnings=[],
                onchain_market=None,
                prepared_at="2026-11-18T00:00:00Z",
            )
            first = ResolutionPlan(
                job_id="job_a",
                evidence_digest="sha256:" + "a" * 64,
                **base,
            )
            second = ResolutionPlan(
                job_id="job_b",
                evidence_digest="sha256:" + "b" * 64,
                **base,
            )
            store.prepare_job(first, now=LATER)
            with self.assertRaises(ResolutionConflict):
                store.prepare_job(second, now=LATER)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
