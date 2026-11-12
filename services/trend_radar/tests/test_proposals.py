import unittest
from datetime import date

from services.trend_radar.models import Category, EligibilityStatus, MarketMode, ProposalStatus
from services.trend_radar.proposals import build_proposals
from services.trend_radar.tests.helpers import FIXED_NOW, make_candidate

SCAN_DATE = date(2026, 11, 11)


def eligible(candidate_id, title, article, score):
    candidate = make_candidate(
        candidate_id=candidate_id,
        title=title,
        settlement_article=article,
        category=Category.AI,
        score=score,
    )
    candidate.eligibility_status = EligibilityStatus.ELIGIBLE
    candidate.discovery_signals["score"] = score
    candidate.discovery_signals["measurement_signature"] = {
        "source": "wikimedia-pageviews-v1",
        "project": "en.wikipedia.org",
        "access": "all-access",
        "agent": "user",
        "metric": "daily_pageviews",
    }
    return candidate


class ProposalTests(unittest.TestCase):
    def test_trend_and_battle_proposals_are_proposed_only(self):
        a = eligible("cand_a", "Topic A", "Topic A", 80)
        b = eligible("cand_b", "Topic B", "Topic B", 70)
        proposals = build_proposals([a, b], scan_date=SCAN_DATE, now=FIXED_NOW)
        self.assertEqual(len(proposals), 3)
        trend = [p for p in proposals if p.mode == MarketMode.TREND_TRADING]
        battle = [p for p in proposals if p.mode == MarketMode.TREND_BATTLE]
        self.assertEqual(len(trend), 2)
        self.assertEqual(len(battle), 1)
        for proposal in proposals:
            self.assertEqual(proposal.status, ProposalStatus.PROPOSED)
            self.assertIsNone(proposal.rule_hash)
            self.assertIn("S3B", proposal.finalization_required)
            self.assertEqual(proposal.created_at, FIXED_NOW)
        self.assertEqual(trend[0].threshold_status, "UNVALIDATED_PROPOSAL")
        self.assertEqual(trend[0].threshold_bps, 1500)
        self.assertEqual(trend[0].observation_window["baseline_date"], "2026-11-14")
        self.assertEqual(trend[0].observation_window["target_date"], "2026-11-21")
        self.assertEqual(battle[0].tie_policy, "void")
        self.assertEqual(battle[0].tie_tolerance_bps, 50)
        self.assertEqual(battle[0].formula, "growth_comparison_v1")
        self.assertIn("trend_battle", a.proposed_market_modes)
        self.assertIn("trend_battle", b.proposed_market_modes)

    def test_no_proposals_for_ineligible_candidates(self):
        candidate = make_candidate(status=EligibilityStatus.NOT_MEASURABLE)
        self.assertEqual(
            build_proposals([candidate], scan_date=SCAN_DATE, now=FIXED_NOW), []
        )

    def test_incompatible_measurements_do_not_form_a_battle(self):
        a = eligible("cand_a", "Topic A", "Topic A", 80)
        b = eligible("cand_b", "Topic B", "Topic B", 70)
        b.discovery_signals["measurement_signature"] = {
            "source": "wikimedia-pageviews-v1",
            "project": "de.wikipedia.org",
            "access": "all-access",
            "agent": "user",
            "metric": "daily_pageviews",
        }
        proposals = build_proposals([a, b], scan_date=SCAN_DATE, now=FIXED_NOW)
        self.assertEqual(
            [p.mode for p in proposals], [MarketMode.TREND_TRADING, MarketMode.TREND_TRADING]
        )

    def test_proposal_ids_are_deterministic(self):
        a = eligible("cand_a", "Topic A", "Topic A", 80)
        one = build_proposals([a], scan_date=SCAN_DATE, now=FIXED_NOW)
        two = build_proposals([a], scan_date=SCAN_DATE, now=FIXED_NOW)
        self.assertEqual(one[0].proposal_id, two[0].proposal_id)
        self.assertTrue(one[0].proposal_id.startswith("prop_"))

    def test_proposal_limits(self):
        candidates = [
            eligible(f"cand_{index}", f"Topic {index}", f"Topic {index}", 90 - index)
            for index in range(12)
        ]
        proposals = build_proposals(
            candidates,
            scan_date=SCAN_DATE,
            now=FIXED_NOW,
            proposal_limit=3,
            battle_limit=1,
        )
        self.assertEqual(len([p for p in proposals if p.mode == MarketMode.TREND_TRADING]), 3)
        self.assertEqual(len([p for p in proposals if p.mode == MarketMode.TREND_BATTLE]), 1)


if __name__ == "__main__":
    unittest.main()
