import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from services.trend_radar.models import (
    Decision,
    EligibilityStatus,
    ProposalStatus,
    SourceStatus,
)
from services.trend_radar.proposals import build_proposals
from services.trend_radar.store import RadarStore
from services.trend_radar.tests.helpers import FIXED_NOW, make_candidate, make_health


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "radar.sqlite3"
        self.store = RadarStore(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_scan_run_lifecycle_and_duplicate_protection(self):
        fingerprint = "fp"
        self.store.start_scan("scan_1", fingerprint, ["wikimedia"], FIXED_NOW)
        self.assertIsNotNone(self.store.running_scan(FIXED_NOW))
        self.assertEqual(
            self.store.recent_completed_scan(fingerprint, FIXED_NOW - timedelta(minutes=1)),
            None,
        )
        self.store.complete_scan("scan_1", {"ok": True}, FIXED_NOW)
        recent = self.store.recent_completed_scan(
            fingerprint, FIXED_NOW - timedelta(minutes=1)
        )
        self.assertIsNotNone(recent)
        self.assertEqual(recent["scan_id"], "scan_1")
        self.assertIsNone(self.store.running_scan(FIXED_NOW))

    def test_stale_running_scan_is_expired(self):
        self.store.start_scan("scan_old", "fp", ["wikimedia"], FIXED_NOW - timedelta(hours=1))
        self.assertIsNone(self.store.running_scan(FIXED_NOW, timeout_seconds=60))

    def test_source_health_preserves_last_success(self):
        healthy = make_health("wikimedia", status=SourceStatus.OK)
        self.store.save_source_health(healthy)
        failed = make_health("wikimedia", status=SourceStatus.FAILED)
        failed.last_success_at = None
        failed.error = "down"
        self.store.save_source_health(failed)
        health = self.store.source_health()[0]
        self.assertEqual(health["status"], "failed")
        self.assertEqual(health["last_success_at"], "2026-11-11T23:45:00Z")

    def test_source_snapshot_is_retained(self):
        self.store.save_source_snapshot("wikimedia", {"v": 1}, FIXED_NOW, "hash1", "2026-11-10")
        self.assertEqual(self.store.get_source_snapshot("wikimedia")["payload"], {"v": 1})
        self.store.save_source_snapshot("wikimedia", {"v": 2}, FIXED_NOW, "hash2", "2026-11-11")
        self.assertEqual(self.store.get_source_snapshot("wikimedia")["payload"], {"v": 2})

    def test_candidate_upsert_and_lookup(self):
        candidate = make_candidate(candidate_id="cand_a", title="A", score=50)
        candidate.eligibility_status = EligibilityStatus.ELIGIBLE
        self.store.upsert_candidate(candidate)
        self.assertEqual(self.store.get_candidate("cand_a")["title"], "A")
        self.assertEqual(self.store.previous_first_seen()["test:cand_a"], FIXED_NOW)
        filtered = self.store.list_candidates(eligibility="ELIGIBLE")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(self.store.list_candidates(eligibility="NOT_MEASURABLE"), [])

    def test_proposal_decision_persists_and_is_reviewable(self):
        candidate = make_candidate(
            candidate_id="cand_a",
            title="Topic A",
            settlement_article="Topic A",
            score=80,
            status=EligibilityStatus.ELIGIBLE,
        )
        proposal = build_proposals(
            [candidate], scan_date=date(2026, 11, 11), now=FIXED_NOW
        )[0]
        self.store.upsert_proposal(proposal, FIXED_NOW)
        updated = self.store.review_proposal(
            proposal.proposal_id,
            Decision.APPROVE,
            "eligible for S3B review",
            "operator-1",
            FIXED_NOW,
        )
        self.assertEqual(updated["status"], "APPROVED")
        self.assertEqual(updated["decision_reason"], "eligible for S3B review")
        self.assertEqual(updated["decided_by"], "operator-1")

        # A later scan regenerates the same proposal ID; the decision survives.
        self.store.apply_existing_decision(proposal)
        self.store.upsert_proposal(proposal, FIXED_NOW + timedelta(minutes=5))
        persisted = self.store.get_proposal(proposal.proposal_id)
        self.assertEqual(persisted["status"], ProposalStatus.APPROVED.value)
        self.assertEqual(persisted["decision_reason"], "eligible for S3B review")

        rejected = self.store.review_proposal(
            proposal.proposal_id,
            Decision.REJECT,
            "operator changed mind",
            "operator-2",
            FIXED_NOW + timedelta(minutes=6),
        )
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(rejected["decision_reason"], "operator changed mind")

    def test_review_requires_reason(self):
        candidate = make_candidate(
            candidate_id="cand_a",
            title="Topic A",
            settlement_article="Topic A",
            status=EligibilityStatus.ELIGIBLE,
        )
        proposal = build_proposals(
            [candidate], scan_date=date(2026, 11, 11), now=FIXED_NOW
        )[0]
        self.store.upsert_proposal(proposal, FIXED_NOW)
        with self.assertRaises(ValueError):
            self.store.review_proposal(
                proposal.proposal_id, Decision.APPROVE, "  ", "op", FIXED_NOW
            )

    def test_review_unknown_proposal(self):
        with self.assertRaises(KeyError):
            self.store.review_proposal(
                "prop_missing", Decision.APPROVE, "reason", "op", FIXED_NOW
            )


if __name__ == "__main__":
    unittest.main()
