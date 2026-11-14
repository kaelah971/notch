"""Service tests for S5 fallback, AI validation, cache and determinism."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.near_ai.client import (
    AIModel,
    AICompletion,
    NearAIModelUnavailable,
    NearAIProviderError,
)
from services.near_ai.config import NearAIConfig
from services.near_ai.grounding import build_market_context, build_radar_context
from services.near_ai.models import GenerationStatus
from services.near_ai.service import BriefService
from services.near_ai.store import BriefStore
from services.near_ai.tests import fixtures


MODEL = AIModel.from_provider(
    {
        "id": "z-ai/glm-5.3-flash",
        "owned_by": "nearai",
        "pricing": {"input": 0.08, "output": 0.5},
        "context_length": 1048576,
        "max_output_length": 1048576,
        "supported_features": ["structured_outputs", "json_mode"],
        "is_ready": True,
    }
)


class FakeClient:
    def __init__(self, *, content=None, model=MODEL, error=None, model_error=None):
        self.content = content
        self.model = model
        self.error = error
        self.model_error = model_error
        self.select_calls = 0
        self.chat_calls = 0

    def list_models(self):
        return [self.model]

    def select_model(self, model_id=None):
        self.select_calls += 1
        if self.model_error:
            raise self.model_error
        return self.model

    def chat_json(self, *, model, system_prompt, user_prompt, **kwargs):
        self.chat_calls += 1
        if self.error:
            raise self.error
        return AICompletion(
            content=self.content,
            text="{}",
            model=model,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            request_id="req-test",
        )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BriefStore(Path(self.tmp.name) / "briefs.sqlite3")
        self.radar_context = build_radar_context(fixtures.candidate())
        self.market_context = build_market_context(
            {"rule": fixtures.rule_trend()},
            fixtures.evidence_trend(),
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def service(self, client, *, key="test-key", max_calls=2):
        config = NearAIConfig(
            api_key=key,
            model="z-ai/glm-5.3-flash",
            data_dir=self.tmp.name,
            rate_limit_seconds=0,
            max_calls_per_run=max_calls,
        )
        return BriefService(
            config=config,
            client=client,
            store=self.store,
            now_fn=lambda: __import__("datetime").datetime(
                2026, 11, 12, 9, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        )

    def test_no_key_returns_grounded_fallback(self):
        client = FakeClient(content=fixtures.valid_ai_content(self.radar_context))
        service = self.service(client, key=None)
        brief = service._generate(self.radar_context, force=False)
        self.assertEqual(brief.generation_status, GenerationStatus.NON_AI_FALLBACK.value)
        self.assertEqual(brief.provider, "deterministic")
        self.assertEqual(brief.model, "none")
        self.assertEqual(brief.inference["status"], "DETERMINISTIC_FALLBACK")
        self.assertIn("123,851", brief.headline)
        self.assertEqual(client.chat_calls, 0)
        self.assertTrue(brief.fallback_reason)

    def test_ai_success_and_cache(self):
        client = FakeClient(content=fixtures.valid_ai_content(self.radar_context))
        service = self.service(client)
        brief = service._generate(self.radar_context, force=False)
        self.assertEqual(brief.generation_status, GenerationStatus.AI_GENERATED.value)
        self.assertEqual(brief.provider, "near-ai")
        self.assertEqual(brief.model, "z-ai/glm-5.3-flash")
        self.assertEqual(brief.inference["status"], "LIVE_AI_VERIFIED")
        self.assertEqual(client.chat_calls, 1)
        self.assertIn("estimated_cost_usd", brief.usage)
        cached = service._generate(self.radar_context, force=False)
        self.assertTrue(cached.cache_hit)
        self.assertEqual(cached.brief_id, brief.brief_id)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(self.store.count(), 1)

    def test_invalid_ai_output_falls_back(self):
        content = fixtures.valid_ai_content(self.radar_context)
        content["summary"] = "Nvidia drew 999 views."
        client = FakeClient(content=content)
        service = self.service(client)
        brief = service._generate(self.radar_context, force=False)
        self.assertEqual(
            brief.generation_status, GenerationStatus.INVALID_AI_FALLBACK.value
        )
        self.assertEqual(brief.provider, "deterministic")
        self.assertEqual(brief.inference["status"], "DETERMINISTIC_FALLBACK")
        self.assertIn("UNSUPPORTED_NUMBER", brief.fallback_reason)
        self.assertEqual(client.chat_calls, 1)

    def test_provider_error_falls_back_without_retry_and_preserves_safe_diagnostics(self):
        client = FakeClient(
            error=NearAIProviderError(
                "unavailable",
                retryable=True,
                diagnostics={
                    "http_status": 200,
                    "finish_reason": "length",
                    "reasoning_content_present": True,
                    "reasoning_content_chars": 18,
                },
            )
        )
        service = self.service(client)
        brief = service._generate(self.radar_context, force=False)
        self.assertEqual(
            brief.generation_status, GenerationStatus.AI_UNAVAILABLE_FALLBACK.value
        )
        self.assertEqual(client.chat_calls, 1)
        self.assertIn("unavailable", brief.fallback_reason)
        self.assertEqual(brief.usage["model_diagnostics"]["finish_reason"], "length")
        self.assertEqual(brief.usage["model_diagnostics"]["reasoning_content_chars"], 18)

    def test_model_unavailable_falls_back_without_chat(self):
        client = FakeClient(model_error=NearAIModelUnavailable("missing", code="MODEL_NOT_FOUND"))
        service = self.service(client)
        brief = service._generate(self.radar_context, force=False)
        self.assertEqual(
            brief.generation_status, GenerationStatus.AI_UNAVAILABLE_FALLBACK.value
        )
        self.assertEqual(client.chat_calls, 0)
        self.assertIn("missing", brief.fallback_reason)

    def test_market_resolution_is_deterministic(self):
        client = FakeClient(content=fixtures.valid_ai_content(self.market_context))
        service = self.service(client)
        brief = service._generate(self.market_context, force=False)
        self.assertEqual(brief.brief_type, "market")
        self.assertIsNotNone(brief.resolution)
        assert brief.resolution is not None
        self.assertEqual(brief.resolution.outcome, "UP")
        self.assertEqual(brief.resolution.rule_hash, fixtures.evidence_trend()["rule_hash"])
        self.assertEqual(brief.resolution.evidence_digest, fixtures.evidence_trend()["evidence_digest"])

    def test_ai_cannot_alter_market_outcome(self):
        content = fixtures.valid_ai_content(self.market_context)
        content["outcome"] = "DOWN"
        client = FakeClient(content=content)
        service = self.service(client)
        brief = service._generate(self.market_context, force=False)
        self.assertEqual(
            brief.generation_status, GenerationStatus.INVALID_AI_FALLBACK.value
        )
        assert brief.resolution is not None
        self.assertEqual(brief.resolution.outcome, "UP")

    def test_per_run_call_limit(self):
        client = FakeClient(content=fixtures.valid_ai_content(self.radar_context))
        service = self.service(client, max_calls=1)
        first = service._generate(self.radar_context, force=False)
        self.assertEqual(first.generation_status, GenerationStatus.AI_GENERATED.value)
        second_context = build_radar_context(fixtures.candidate_without_coverage())
        second = service._generate(second_context, force=False)
        self.assertEqual(
            second.generation_status, GenerationStatus.AI_UNAVAILABLE_FALLBACK.value
        )
        self.assertIn("per-run", second.fallback_reason)
        self.assertEqual(client.chat_calls, 1)

    def test_read_only_does_not_call_ai(self):
        client = FakeClient(content=fixtures.valid_ai_content(self.radar_context))
        service = self.service(client)
        brief = service._generate(self.radar_context, force=False, allow_ai=False)
        self.assertEqual(brief.generation_status, GenerationStatus.NON_AI_FALLBACK.value)
        self.assertEqual(client.chat_calls, 0)
        self.assertIn("disabled", brief.fallback_reason)

    def test_status_checks_catalog_without_inference(self):
        client = FakeClient()
        service = self.service(client)
        status = service.status()
        self.assertTrue(status["key_present"])
        self.assertTrue(status["model_verified"])
        self.assertEqual(status["catalog_count"], 1)
        self.assertEqual(client.chat_calls, 0)


if __name__ == "__main__":
    unittest.main()
