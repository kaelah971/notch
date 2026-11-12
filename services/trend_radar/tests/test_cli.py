import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "radar"
        self.env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "services.trend_radar",
                "--data-dir",
                str(self.data_dir),
                *args,
            ],
            cwd=REPO_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    def test_scan_summary_and_persisted_commands(self):
        scan = self.run_cli("scan", "--fixtures", str(FIXTURES), "--summary")
        self.assertEqual(scan.returncode, 0, scan.stderr)
        self.assertIn("source health", scan.stdout)
        self.assertIn("Nvidia", scan.stdout)
        self.assertTrue((self.data_dir / "last_scan.json").exists())

        candidates = self.run_cli("candidates", "--summary", "--limit", "10")
        self.assertEqual(candidates.returncode, 0, candidates.stderr)
        self.assertIn("Nvidia", candidates.stdout)

        proposals = self.run_cli("proposals")
        self.assertEqual(proposals.returncode, 0, proposals.stderr)
        listed = json.loads(proposals.stdout)
        self.assertTrue(listed)
        proposal_id = listed[0]["proposal"]["proposal_id"]

        review = self.run_cli(
            "review",
            proposal_id,
            "--approve",
            "--reason",
            "reviewed in CLI test",
        )
        self.assertEqual(review.returncode, 0, review.stderr)
        reviewed = json.loads(review.stdout)
        self.assertEqual(reviewed["status"], "APPROVED")
        self.assertEqual(reviewed["decision_reason"], "reviewed in CLI test")

        approved = self.run_cli("proposals", "--status", "APPROVED", "--summary")
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertIn(proposal_id, approved.stdout)

    def test_scan_is_deduplicated_on_second_call(self):
        first = self.run_cli("scan", "--fixtures", str(FIXTURES), "--summary")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli("scan", "--fixtures", str(FIXTURES), "--summary")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("deduplicated: True", second.stdout)

    def test_unknown_candidate_and_missing_reason_errors(self):
        show = self.run_cli("show", "cand_missing")
        self.assertNotEqual(show.returncode, 0)
        scan = self.run_cli("scan", "--fixtures", str(FIXTURES), "--summary")
        self.assertEqual(scan.returncode, 0, scan.stderr)
        proposals = json.loads(self.run_cli("proposals").stdout)
        proposal_id = proposals[0]["proposal"]["proposal_id"]
        missing_reason = self.run_cli("review", proposal_id, "--approve", "--reason", " ")
        self.assertNotEqual(missing_reason.returncode, 0)


if __name__ == "__main__":
    unittest.main()
