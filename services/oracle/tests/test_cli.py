import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from services.oracle.tests.helpers import FIXTURES, REPO_ROOT, fake_market


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "oracle"
        self.env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        demo = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "--now",
            "2026-11-12T02:00:00Z",
            "--fixtures",
            str(FIXTURES),
            "demo",
            "--summary",
        )
        self.assertEqual(demo.returncode, 0, demo.stderr)
        self.assertIn("onchain_actions=none", demo.stdout)
        self.demo = json.loads((self.data_dir / "demo.json").read_text(encoding="utf-8"))
        self.by_name = {item["name"]: item for item in self.demo["rules"]}

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "services.oracle", *args],
            cwd=REPO_ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    def test_demo_verify_and_mutation_detection(self):
        evidence_path = self.by_name["replay_trend_nvidia"]["evidence"]["path"]
        verified = self.run_cli("verify-evidence", evidence_path)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        result = json.loads(verified.stdout)
        self.assertTrue(result["valid"])

        doc = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        topic = doc["topics"][0]["topic_id"]
        doc["observations"][topic]["baseline"]["views"] += 1
        tampered = Path(self.data_dir) / "tampered.json"
        tampered.write_text(json.dumps(doc), encoding="utf-8")
        broken = self.run_cli("verify-evidence", str(tampered))
        self.assertEqual(broken.returncode, 1)
        self.assertFalse(json.loads(broken.stdout)["valid"])

    def test_approve_and_prepare_resolution_with_market_json(self):
        item = self.by_name["replay_trend_nvidia"]
        approved = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "--now",
            "2026-11-18T00:00:00Z",
            "approve-rule",
            item["rule_hash"],
            "--reason",
            "approved for test",
            "--operator",
            "test-operator",
        )
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertEqual(json.loads(approved.stdout)["status"], "APPROVED")

        rules = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "rules",
            "--status",
            "APPROVED",
            "--summary",
        )
        self.assertEqual(rules.returncode, 0, rules.stderr)
        self.assertIn(item["rule_hash"], rules.stdout)

        market_path = Path(self.data_dir) / "market.json"
        market_path.write_text(
            json.dumps(fake_market(item["rule"]), ensure_ascii=False), encoding="utf-8"
        )
        prepared = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "--now",
            "2026-11-18T00:00:00Z",
            "prepare-resolution",
            "--rule-hash",
            item["rule_hash"],
            "--evidence-digest",
            item["evidence"]["evidence"]["evidence_digest"],
            "--market-json",
            str(market_path),
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        job = json.loads(prepared.stdout)
        self.assertEqual(job["plan"]["status"], "PREPARED")
        self.assertEqual(job["plan"]["action"], "resolve_market")
        self.assertNotIn("transaction_hash", job["plan"])
        self.assertIn("<resolver-account>", job["plan"]["near_cli_command_template"])

        jobs = self.run_cli("--data-dir", str(self.data_dir), "jobs", "--summary")
        self.assertEqual(jobs.returncode, 0, jobs.stderr)
        self.assertIn(job["plan"]["job_id"], jobs.stdout)

    def test_resolve_replay_rule(self):
        item = self.by_name["replay_battle_bitcoin_chatgpt"]
        resolved = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "--now",
            "2026-11-18T00:00:00Z",
            "--fixtures",
            str(FIXTURES),
            "resolve",
            item["rule_hash"],
        )
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        result = json.loads(resolved.stdout)
        self.assertEqual(result["outcome"], "TOPIC_A")
        self.assertTrue(result["verification"]["valid"])
        self.assertEqual(result["status"], "EVIDENCE_READY")

    def test_unknown_rule_and_invalid_review_errors(self):
        missing = self.run_cli("--data-dir", str(self.data_dir), "show-rule", "sha256:" + "0" * 64)
        self.assertNotEqual(missing.returncode, 0)
        invalid = self.run_cli(
            "--data-dir",
            str(self.data_dir),
            "approve-rule",
            "sha256:" + "0" * 64,
            "--reason",
            "x",
        )
        self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
