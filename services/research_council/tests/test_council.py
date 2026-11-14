"""Phase 5E Research Council tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.near_ai.client import AIModel, AICompletion
from services.near_ai.config import NearAIConfig
from services.near_ai.grounding import build_market_research_context
from services.near_ai.tests import fixtures
from services.research_council.service import (
    ResearchCouncilService,
    CouncilValidationError,
    validate_council_role,
)
from services.research_council.store import ResearchCouncilStore


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def context():
    rule = fixtures.rule_trend()
    rule["market_id"] = "council-test-market"
    record = {
        "rule_hash": "sha256:council-rule",
        "market_id": rule["market_id"],
        "status": "APPROVED",
        "created_at": "2026-11-12T00:00:00Z",
        "rule": rule,
    }
    snapshot = {
        "article": "Nvidia",
        "project": "en.wikipedia.org",
        "access": "all-access",
        "agent": "user",
        "window_start": "2026-11-03",
        "window_end": "2026-11-10",
        "retrieved_at": "2026-11-12T01:00:00Z",
        "source_status": "parsed",
        "missing_dates": [],
        "error": None,
        "source_url": "https://wikimedia.org/example",
        "raw_response_hash": "sha256:raw",
        "observations": [
            {"date": "2026-11-03", "views": 4743, "observation_hash": "sha256:o1", "raw_response_hash": "sha256:raw", "retrieved_at": "2026-11-12T01:00:00Z", "source_url": "https://wikimedia.org/example"},
            {"date": "2026-11-10", "views": 123851, "observation_hash": "sha256:o2", "raw_response_hash": "sha256:raw", "retrieved_at": "2026-11-12T01:00:00Z", "source_url": "https://wikimedia.org/example"},
        ],
    }
    return build_market_research_context(record, None, [snapshot], [])


class CouncilClient:
    def __init__(self, content):
        self.content = content
        self.calls = 0
        self.last_user_prompt = ""
        self.model = AIModel.from_provider({"id": "z-ai/glm-5.3-flash", "is_ready": True})

    def select_model(self, model_id=None):
        return self.model

    def chat_json(self, **kwargs):
        self.calls += 1
        self.last_user_prompt = kwargs.get("user_prompt", "")
        return AICompletion(
            content=self.content,
            text="{}",
            model=self.model.model_id,
            usage={"prompt_tokens": 30, "completion_tokens": 20},
            request_id="req-council-test",
            diagnostics={"choices_count": 1},
        )


class CouncilTests(unittest.TestCase):
    def test_deterministic_council_uses_one_snapshot_and_tracks_audit(self):
        ctx = context()
        with tempfile.TemporaryDirectory() as temp:
            store = ResearchCouncilStore(Path(temp) / "council.sqlite3")
            service = ResearchCouncilService(
                config=NearAIConfig(api_key=None, data_dir=temp, cache_ttl_seconds=3600),
                client=SimpleNamespace(),
                store=store,
                now_fn=lambda: NOW,
            )
            first = service.generate(ctx, allow_ai=True)
            second = service.generate(ctx, allow_ai=True)
            self.assertEqual(first["generation_mode"], "DETERMINISTIC_EVIDENCE_LENSES")
            self.assertFalse(first["ai_call_triggered"])
            self.assertEqual(first["snapshot"]["snapshot_digest"], second["snapshot"]["snapshot_digest"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual({role["snapshot_id"] for role in first["roles"]}, {first["snapshot"]["snapshot_id"]})
            self.assertEqual(first["audit"]["execution_boundary"]["broadcast"], False)
            self.assertEqual(first["disagreement"]["status"], "UP_ONLY")
            self.assertTrue(first["audit"]["audit_id"].startswith("audit_"))
            store.close()

    def test_invalid_citation_is_rejected_before_ai_role_is_accepted(self):
        ctx = context()
        role = {
            "position": "UP",
            "headline": "A bounded lens",
            "thesis": "The snapshot contains a cited observation.",
            "claims": [{"text": "A claim", "kind": "FACT", "evidence_refs": ["invented"]}],
            "counterpoints": [{"text": "Unknown", "kind": "UNKNOWN", "evidence_refs": []}],
            "open_questions": ["What else should be checked?"],
        }
        with self.assertRaises(CouncilValidationError) as caught:
            validate_council_role(role, ctx, "bull_analyst")
        self.assertEqual(caught.exception.code, "UNKNOWN_EVIDENCE_REF")

    def test_mock_ai_generation_is_one_call_and_provenance_is_safe(self):
        ctx = context()
        refs = [ref.ref_id for ref in ctx.evidence_references]
        claim = {"text": "Nvidia pageviews increased across the supplied window.", "kind": "INTERPRETATION", "evidence_refs": refs[-2:]}
        unknown = {"text": "The snapshot does not establish a cause.", "kind": "UNKNOWN", "evidence_refs": []}
        role = {
            "position": "UP",
            "headline": "Cited UP lens",
            "thesis": "The supplied observations support an UP reading without a forecast.",
            "claims": [claim],
            "counterpoints": [unknown],
            "open_questions": ["What independent source should be checked next?"],
        }
        content = {"roles": {
            "bull_analyst": role,
            "bear_analyst": {**role, "position": "NEUTRAL", "headline": "Cited DOWN lens", "thesis": "The supplied observations do not establish DOWN.", "claims": [unknown]},
            "evidence_verifier": {**role, "position": "NEUTRAL", "headline": "Citation check", "thesis": "The verifier checks the supplied references.", "claims": [{"text": "The cited rule reference is in the supplied snapshot.", "kind": "FACT", "evidence_refs": [refs[0]]}]},
        }}
        client = CouncilClient(content)
        with tempfile.TemporaryDirectory() as temp:
            store = ResearchCouncilStore(Path(temp) / "council.sqlite3")
            service = ResearchCouncilService(
                config=NearAIConfig(api_key="configured", data_dir=temp, max_calls_per_run=1, cache_ttl_seconds=3600),
                client=client,
                store=store,
                now_fn=lambda: NOW,
            )
            council = service.generate(ctx, allow_ai=True)
            self.assertEqual(client.calls, 1)
            self.assertIn("123851", client.last_user_prompt)
            self.assertEqual(council["generation_mode"], "AI_GENERATED")
            self.assertEqual(council["roles"][0]["inference"]["request_id"], "req-council-test")
            self.assertEqual(council["roles"][0]["citation_validation"]["status"], "valid")
            self.assertNotIn("configured", repr(council))
            store.close()

    def test_ai_invalid_role_falls_back_without_raw_response(self):
        ctx = context()
        content = {"roles": {
            "bull_analyst": {"position": "UP", "headline": "bad", "thesis": "bad", "claims": [{"text": "bad", "kind": "FACT", "evidence_refs": ["unknown"]}], "counterpoints": [{"text": "unknown", "kind": "UNKNOWN", "evidence_refs": []}], "open_questions": ["check"]},
            "bear_analyst": {},
            "evidence_verifier": {},
        }}
        with tempfile.TemporaryDirectory() as temp:
            store = ResearchCouncilStore(Path(temp) / "council.sqlite3")
            service = ResearchCouncilService(
                config=NearAIConfig(api_key="configured", data_dir=temp, max_calls_per_run=1),
                client=CouncilClient(content),
                store=store,
                now_fn=lambda: NOW,
            )
            council = service.generate(ctx, allow_ai=True)
            self.assertEqual(council["roles"][0]["generation_status"], "INVALID_AI_FALLBACK")
            self.assertTrue(all(role["citation_validation"]["status"] == "valid" for role in council["roles"]))
            self.assertNotIn("unknown", council["roles"][0]["citation_validation"]["invalid_refs"])
            store.close()


if __name__ == "__main__":
    unittest.main()
