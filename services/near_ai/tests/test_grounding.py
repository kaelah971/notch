"""Grounding tests for S3A candidates and S3B evidence."""

from __future__ import annotations

import unittest

from services.near_ai.grounding import build_market_context, build_radar_context
from services.near_ai.tests import fixtures


class GroundingTests(unittest.TestCase):
    def test_radar_context_uses_real_measurements(self):
        context = build_radar_context(fixtures.candidate())
        self.assertEqual(context.brief_type, "radar")
        self.assertEqual(context.topic, "Nvidia")
        self.assertEqual(context.candidate_id, fixtures.CANDIDATE_ID)
        self.assertIsNone(context.market_id)
        self.assertIsNone(context.resolution)
        self.assertEqual(context.measurement_window["start"], "2026-11-04")
        self.assertEqual(context.measurement_window["end"], "2026-11-10")
        self.assertIn("123851", context.allowed_numbers)
        self.assertIn("123,851", context.allowed_numbers)
        self.assertIn("338", context.allowed_numbers)
        self.assertIn("4112", context.allowed_numbers)
        self.assertIn("43298", context.allowed_numbers)
        self.assertIn("2026-11-10", context.allowed_dates)
        self.assertEqual(len(context.evidence_references), 3)
        self.assertIn("Nvidia", context.fallback.headline)
        self.assertIn("123,851", context.fallback.headline)
        self.assertEqual(context.fallback.observed_signals[0].kind, "FACT")
        self.assertTrue(context.fallback.observed_signals[0].evidence_refs)
        self.assertTrue(context.input_digest.startswith("sha256:"))

    def test_radar_context_missing_coverage_is_explicit(self):
        context = build_radar_context(fixtures.candidate_without_coverage())
        self.assertIn("1 source", context.fallback.headline)
        self.assertEqual(context.measurement_window["start"], "2026-11-12T00:21:10.784731Z")
        self.assertTrue(any("No frozen market rule" in item for item in context.fallback.missing_evidence))
        self.assertIn("123851", context.allowed_numbers)

    def test_market_context_preserves_rule_and_outcome(self):
        context = build_market_context(
            {"rule": fixtures.rule_trend()},
            fixtures.evidence_trend(),
        )
        self.assertEqual(context.brief_type, "market")
        self.assertEqual(context.market_id, fixtures.MARKET_ID)
        self.assertEqual(context.candidate_id, fixtures.CANDIDATE_ID)
        self.assertIsNotNone(context.resolution)
        assert context.resolution is not None
        self.assertEqual(context.resolution.outcome, "UP")
        self.assertIn("4,743", context.resolution.text)
        self.assertIn("123,851", context.resolution.text)
        self.assertIn("251,123", context.resolution.text)
        self.assertIn("1,350", context.resolution.text)
        self.assertEqual(context.resolution.rule_hash, fixtures.evidence_trend()["rule_hash"])
        self.assertEqual(context.resolution.evidence_digest, fixtures.evidence_trend()["evidence_digest"])
        self.assertIn("251123", context.allowed_numbers)
        self.assertIn("1350", context.allowed_numbers)
        self.assertIn("2026-11-03", context.allowed_dates)
        self.assertEqual(context.fallback.observed_signals[0].kind, "FACT")
        self.assertTrue(context.fallback.observed_signals[0].evidence_refs)
        self.assertEqual(context.fallback.notable_changes, [])
        self.assertEqual(len(context.evidence_references), 3)

    def test_market_resolution_text_comes_from_rule_not_model(self):
        context = build_market_context(
            {"rule": fixtures.rule_trend()},
            fixtures.evidence_trend(),
        )
        assert context.resolution is not None
        self.assertIn("floor", context.resolution.formula)
        self.assertIn("UP", context.resolution.text)
        self.assertEqual(context.resolution.observation_window["baseline_date"], "2026-11-03")
        self.assertEqual(context.resolution.observation_window["target_date"], "2026-11-10")


if __name__ == "__main__":
    unittest.main()
