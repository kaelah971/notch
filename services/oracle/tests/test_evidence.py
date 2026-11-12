import copy
import dataclasses
import tempfile
import unittest
from datetime import date

from services.oracle.evidence import (
    build_evidence,
    evidence_digest,
    evidence_to_dict,
    save_evidence,
    verify_evidence,
)
from services.oracle.rules import rule_digest, validate_rule
from services.oracle.tests.helpers import FIXED_NOW, make_service


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.service, cls.store, cls.fetcher = make_service(cls.temp.name)
        cls.demo = cls.service.demo(now=FIXED_NOW)
        cls.rules = {item["name"]: item for item in cls.demo["rules"]}
        cls.ranges = cls.service.load_ranges(
            ["Bitcoin", "ChatGPT", "Nvidia"],
            date(2026, 9, 1),
            date(2026, 11, 10),
        )
        cls.trend_rule = cls.rules["replay_trend_nvidia"]["rule"]
        cls.battle_rule = cls.rules["replay_battle_bitcoin_chatgpt"]["rule"]

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.temp.cleanup()

    def test_replay_evidence_is_reproducible_and_verified(self):
        first = build_evidence(self.trend_rule, self.ranges)
        second = build_evidence(self.trend_rule, self.ranges)
        self.assertEqual(first.outcome, "UP")
        self.assertEqual(first.calculation["growth_bps"], 251123)
        self.assertEqual(first.evidence_digest, second.evidence_digest)
        self.assertRegex(first.evidence_digest, r"^sha256:[0-9a-f]{64}$")
        verification = verify_evidence(
            evidence_to_dict(first), expected_rule_hash=rule_digest(self.trend_rule)
        )
        self.assertTrue(verification["valid"], verification["reasons"])
        self.assertEqual(len(first.raw_source_hashes), 1)
        self.assertIn("integrity", first.integrity_note.casefold())

    def test_mutating_an_observation_invalidates_digest(self):
        evidence = evidence_to_dict(build_evidence(self.trend_rule, self.ranges))
        tampered = copy.deepcopy(evidence)
        topic = tampered["topics"][0]["topic_id"]
        tampered["observations"][topic]["baseline"]["views"] += 1
        result = verify_evidence(tampered)
        self.assertFalse(result["valid"])
        self.assertIn("digest_mismatch", result["reasons"])
        self.assertTrue(
            any(reason.startswith("observation_hash_mismatch") for reason in result["reasons"])
        )

    def test_recomputed_digest_still_detects_observation_hash_mismatch(self):
        evidence = evidence_to_dict(build_evidence(self.trend_rule, self.ranges))
        tampered = copy.deepcopy(evidence)
        topic = tampered["topics"][0]["topic_id"]
        tampered["observations"][topic]["baseline"]["views"] += 1
        tampered["evidence_digest"] = evidence_digest(tampered)
        result = verify_evidence(tampered)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any(reason.startswith("observation_hash_mismatch") for reason in result["reasons"])
        )

    def test_exact_threshold_and_outcome_recomputation(self):
        growth = build_evidence(self.trend_rule, self.ranges).calculation["growth_bps"]
        exact_rule = copy.deepcopy(self.trend_rule)
        exact_rule["formula"]["threshold_bps"] = growth
        exact = build_evidence(exact_rule, self.ranges)
        self.assertEqual(exact.outcome, "UP")
        above_rule = copy.deepcopy(self.trend_rule)
        above_rule["formula"]["threshold_bps"] = growth + 1
        above = build_evidence(above_rule, self.ranges)
        self.assertEqual(above.outcome, "DOWN")
        self.assertNotEqual(exact.evidence_digest, above.evidence_digest)
        self.assertTrue(verify_evidence(evidence_to_dict(exact))["valid"])
        self.assertTrue(verify_evidence(evidence_to_dict(above))["valid"])

    def test_battle_evidence_and_tie(self):
        evidence = build_evidence(self.battle_rule, self.ranges)
        self.assertEqual(evidence.outcome, "TOPIC_A")
        self.assertEqual(evidence.calculation["difference_bps"], 6551)
        self.assertTrue(
            verify_evidence(
                evidence_to_dict(evidence),
                expected_rule_hash=rule_digest(self.battle_rule),
            )["valid"]
        )
        tie_rule = copy.deepcopy(self.battle_rule)
        tie_rule["formula"]["tie_tolerance_bps"] = 7000
        tie = build_evidence(tie_rule, self.ranges)
        self.assertEqual(tie.outcome, "TIE")
        self.assertTrue(verify_evidence(evidence_to_dict(tie))["valid"])

    def test_missing_target_is_invalid_not_a_winner(self):
        missing_rule = copy.deepcopy(self.trend_rule)
        missing_rule["market_id"] = "s3b-test-missing-target"
        missing_rule["observation"]["target_date"] = "2026-11-11"
        self.assertEqual(validate_rule(missing_rule), [])
        evidence = build_evidence(missing_rule, self.ranges)
        self.assertEqual(evidence.outcome, "INVALID")
        self.assertEqual(evidence.invalidity_reason, "missing_target_observation")
        result = verify_evidence(evidence_to_dict(evidence))
        self.assertTrue(result["valid"], result["reasons"])

    def test_low_baseline_is_invalid(self):
        ranges = copy.deepcopy(self.ranges)
        baseline = self.ranges["Nvidia"].observations["2026-11-03"]
        mutated = dataclasses.replace(baseline, views=100)
        from services.oracle.wikimedia import observation_hash

        mutated.observation_hash = observation_hash(mutated)
        ranges["Nvidia"].observations["2026-11-03"] = mutated
        evidence = build_evidence(self.trend_rule, ranges)
        self.assertEqual(evidence.outcome, "INVALID")
        self.assertEqual(evidence.invalidity_reason, "baseline_below_minimum")
        self.assertTrue(verify_evidence(evidence_to_dict(evidence))["valid"])

    def test_expected_rule_hash_mismatch(self):
        evidence = evidence_to_dict(build_evidence(self.trend_rule, self.ranges))
        result = verify_evidence(evidence, expected_rule_hash="sha256:" + "0" * 64)
        self.assertFalse(result["valid"])
        self.assertIn("rule_hash_mismatch", result["reasons"])

    def test_incomplete_source_window_is_invalid(self):
        ranges = copy.deepcopy(self.ranges)
        ranges["Nvidia"].observations.pop("2026-11-10")
        ranges["Nvidia"].missing_dates.append("2026-11-10")
        evidence = build_evidence(self.trend_rule, ranges)
        self.assertEqual(evidence.outcome, "INVALID")
        self.assertEqual(evidence.invalidity_reason, "missing_source_observations")
        self.assertTrue(verify_evidence(evidence_to_dict(evidence))["valid"])

    def test_save_evidence_round_trip(self):
        evidence = build_evidence(self.trend_rule, self.ranges)
        path = save_evidence(evidence, self.temp.name + "/evidence")
        self.assertTrue(path.exists())
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(verify_evidence(doc)["valid"])


if __name__ == "__main__":
    unittest.main()
