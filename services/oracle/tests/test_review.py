import copy
import dataclasses
import unittest
from datetime import date

from services.oracle.calibration import calibrate_battle, calibrate_trend
from services.oracle.review import (
    CandidateRepository,
    relationship_flags,
    review_battle_pair,
    review_candidate,
)
from services.oracle.tests.helpers import S3A_EVIDENCE, fixture_fetcher
from services.oracle.wikimedia import fetch_range


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fetcher = fixture_fetcher()
        cls.ranges = {
            article: fetch_range(
                fetcher,
                article=article,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 11, 10),
            )
            for article in ("Bitcoin", "ChatGPT", "Nvidia")
        }
        cls.repo = CandidateRepository(S3A_EVIDENCE)
        cls.btc = cls.repo.get_by_title("Bitcoin")
        cls.cg = cls.repo.get_by_title("ChatGPT")
        cls.nv = cls.repo.get_by_title("Nvidia")
        cls.btc_cal = calibrate_trend(
            cls.ranges["Bitcoin"],
            baseline_date=date(2026, 11, 3),
            target_date=date(2026, 11, 10),
            calibration_end=date(2026, 11, 2),
            replay=True,
        )
        cls.nv_cal = calibrate_trend(
            cls.ranges["Nvidia"],
            baseline_date=date(2026, 11, 3),
            target_date=date(2026, 11, 10),
            calibration_end=date(2026, 11, 2),
            replay=True,
        )
        cls.battle_cal = calibrate_battle(
            cls.ranges["Bitcoin"],
            cls.ranges["ChatGPT"],
            baseline_date=date(2026, 11, 3),
            target_date=date(2026, 11, 10),
            calibration_end=date(2026, 11, 2),
            replay=True,
        )

    def test_shortlist_reviews_are_ready_but_never_approved(self):
        for candidate, cal in [
            (self.btc, self.btc_cal),
            (self.cg, self.cg_cal if hasattr(self, "cg_cal") else self.btc_cal),
            (self.nv, self.nv_cal),
        ]:
            report = review_candidate(candidate, calibration=cal)
            self.assertTrue(report.measurement_valid)
            self.assertTrue(report.operator_approval_required)
            self.assertNotEqual(report.recommendation, "APPROVED")
            self.assertIn(report.recommendation, {"READY_FOR_OPERATOR_REVIEW", "READY_FOR_OPERATOR_REVIEW_FUTURE"})

    def test_low_popularity_does_not_reject_measurement(self):
        low = dataclasses.replace(self.btc_cal, baseline_views=2000)
        low = dataclasses.replace(low, min_baseline_views=1000)
        report = review_candidate(self.btc, calibration=low)
        self.assertTrue(report.measurement_valid)
        self.assertEqual(report.market_interest, "low_but_measurable")
        self.assertEqual(report.recommendation, "READY_FOR_OPERATOR_REVIEW")

    def test_nvidia_and_jensen_is_correlated(self):
        jensen = self.repo.get_by_title("Jensen Huang")
        self.assertIsNotNone(jensen)
        flags = relationship_flags(self.nv, jensen)
        self.assertTrue(any(flag["type"] == "company_ceo" for flag in flags))
        report = review_battle_pair(self.nv, jensen, calibration=self.nv_cal)
        self.assertEqual(report.recommendation, "REJECT_CORRELATED_TOPICS")
        self.assertTrue(report.operator_approval_required)

    def test_same_entity_and_alias_overlap(self):
        duplicate = copy.deepcopy(self.btc)
        duplicate["candidate_id"] = "cand_duplicate"
        flags = relationship_flags(self.btc, duplicate)
        self.assertTrue(any(flag["type"] == "same_entity" for flag in flags))
        report = review_battle_pair(self.btc, duplicate, calibration=self.btc_cal)
        self.assertEqual(report.recommendation, "REJECT_CORRELATED_TOPICS")

    def test_parent_child_topic(self):
        child = copy.deepcopy(self.btc)
        child["candidate_id"] = "cand_history_btc"
        child["canonical_topic_id"] = "wiki:en.wikipedia.org:history-of-bitcoin"
        child["title"] = "History of Bitcoin"
        child["discovery_signals"]["settlement_article"] = "History of Bitcoin"
        child["discovery_signals"]["settlement_page_id"] = 999
        child["aliases"] = ["History of Bitcoin"]
        flags = relationship_flags(self.btc, child)
        self.assertTrue(any(flag["type"] == "parent_child_topic" for flag in flags))

    def test_sensitive_death_topic_is_flagged(self):
        sensitive = copy.deepcopy(self.btc)
        sensitive["candidate_id"] = "cand_sensitive"
        sensitive["title"] = "Bitcoin death"
        sensitive["aliases"] = ["Bitcoin death"]
        sensitive["discovery_signals"]["settlement_article"] = "Bitcoin death"
        sensitive["discovery_signals"]["settlement_page_id"] = 999
        report = review_candidate(sensitive, calibration=self.btc_cal)
        self.assertTrue(
            any(flag["type"] == "death_or_tragedy" for flag in report.sensitivity_flags)
        )
        self.assertEqual(report.recommendation, "HOLD_FOR_OPERATOR_REVIEW")
        self.assertTrue(report.operator_approval_required)

    def test_redirect_is_ambiguous(self):
        candidate = copy.deepcopy(self.btc)
        candidate["source_identities"][0]["redirected_from"] = "BTC"
        report = review_candidate(candidate, calibration=self.btc_cal)
        self.assertTrue(report.ambiguous_mapping)
        self.assertEqual(report.recommendation, "HOLD_FOR_OPERATOR_REVIEW")

    def test_bitcoin_chatgpt_pair_is_ready(self):
        report = review_battle_pair(self.btc, self.cg, calibration=self.battle_cal)
        self.assertEqual(report.recommendation, "READY_FOR_OPERATOR_REVIEW")
        self.assertFalse(report.relationship_flags)
        self.assertTrue(report.operator_approval_required)


if __name__ == "__main__":
    unittest.main()
