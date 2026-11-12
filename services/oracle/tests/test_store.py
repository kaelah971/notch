import tempfile
import unittest
from datetime import date

from services.oracle.calibration import calibrate_trend
from services.oracle.review import CandidateRepository, review_candidate
from services.oracle.store import OracleStore
from services.oracle.tests.helpers import FIXED_NOW, S3A_EVIDENCE, fixture_fetcher
from services.oracle.wikimedia import fetch_range


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = OracleStore(self.temp.name + "/oracle.sqlite3")
        fetcher = fixture_fetcher()
        self.range = fetch_range(
            fetcher,
            article="Nvidia",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 10),
        )
        self.calibration = calibrate_trend(
            self.range,
            baseline_date=date(2026, 11, 3),
            target_date=date(2026, 11, 10),
            calibration_end=date(2026, 11, 2),
            replay=True,
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_calibration_round_trip(self):
        saved = self.store.save_calibration(self.calibration, now=FIXED_NOW)
        self.assertEqual(saved["report_digest"], self.calibration.report_digest)
        repeated = self.store.save_calibration(self.calibration, now=FIXED_NOW)
        self.assertEqual(repeated["report_digest"], saved["report_digest"])
        self.assertEqual(len(self.store.list_calibrations()), 1)
        self.assertEqual(
            self.store.get_calibration(self.calibration.report_digest)["calibration"][
                "suggested_threshold_bps"
            ],
            1350,
        )

    def test_review_round_trip(self):
        repo = CandidateRepository(S3A_EVIDENCE)
        review = review_candidate(repo.get_by_title("Nvidia"), calibration=self.calibration)
        saved = self.store.save_review(review, now=FIXED_NOW)
        self.assertTrue(saved["review_id"].startswith("review_"))
        listed = self.store.list_reviews()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["review"]["recommendation"], review.recommendation)
        self.assertTrue(listed[0]["review"]["operator_approval_required"])


if __name__ == "__main__":
    unittest.main()
