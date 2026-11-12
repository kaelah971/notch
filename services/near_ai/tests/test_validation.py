"""Validation tests for grounded structured AI output."""

from __future__ import annotations

import copy
import unittest

from services.near_ai.grounding import build_market_context, build_radar_context
from services.near_ai.tests import fixtures
from services.near_ai.validation import (
    BriefValidationError,
    extract_numbers,
    validate_brief_draft,
)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.radar = build_radar_context(fixtures.candidate())
        self.market = build_market_context(
            {"rule": fixtures.rule_trend()},
            fixtures.evidence_trend(),
        )

    def test_valid_radar_draft(self):
        draft = validate_brief_draft(fixtures.valid_ai_content(self.radar), self.radar)
        self.assertIn("123,851", draft.headline)
        self.assertEqual(draft.observed_signals[0].kind, "FACT")
        self.assertTrue(draft.observed_signals[0].evidence_refs)

    def test_valid_market_draft(self):
        draft = validate_brief_draft(fixtures.valid_ai_content(self.market), self.market)
        self.assertEqual(draft.headline, "Historical replay: Nvidia outcome UP")
        self.assertEqual(draft.uncertainty[0].kind, "UNKNOWN")

    def test_unsupported_number_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["summary"] = "Nvidia drew 999 views."
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_NUMBER")

    def test_unsupported_date_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["summary"] = "Nvidia drew attention on 2026-12-01."
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_DATE")

    def test_unknown_evidence_ref_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["observed_signals"][0]["evidence_refs"] = ["unknown-ref"]
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "UNKNOWN_EVIDENCE_REF")

    def test_fact_requires_evidence_ref(self):
        content = fixtures.valid_ai_content(self.radar)
        content["observed_signals"][0]["evidence_refs"] = []
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "MISSING_EVIDENCE_REF")

    def test_invalid_kind_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["observed_signals"][0]["kind"] = "OPINION"
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "INVALID_KIND")

    def test_unknown_field_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["winning_outcome"] = 0
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "UNKNOWN_FIELD")

    def test_missing_field_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        del content["summary"]
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "MISSING_FIELD")

    def test_banned_certainty_rejected(self):
        content = fixtures.valid_ai_content(self.radar)
        content["summary"] = "This is guaranteed profit."
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.radar)
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_CLAIM")

    def test_market_outcome_tamper_rejected(self):
        content = fixtures.valid_ai_content(self.market)
        content["outcome"] = "DOWN"
        with self.assertRaises(BriefValidationError) as ctx:
            validate_brief_draft(content, self.market)
        self.assertEqual(ctx.exception.code, "UNKNOWN_FIELD")

    def test_extract_numbers(self):
        numbers, dates = extract_numbers("Views 123,851 on 2026-11-10; delta -4,931.")
        self.assertIn("123851", numbers)
        self.assertIn("-4931", numbers)
        self.assertIn("2026-11-10", dates)


if __name__ == "__main__":
    unittest.main()
