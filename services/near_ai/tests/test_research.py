"""Phase 5A market research grounding tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.near_ai.client import AICompletion, AIModel
from services.near_ai.config import NearAIConfig
from services.near_ai.grounding import build_market_research_context
from services.near_ai.prompt import build_prompts
from services.near_ai.service import BriefService
from services.near_ai.store import BriefStore
from services.near_ai.tests import fixtures
from services.near_ai.validation import BriefValidationError, validate_brief_draft
from services.trend_radar.http import FetchResult


class ResearchFetcher:
    def get_json(self, url, *, source, cache_key, ttl_seconds, allow_stale):
        article = "Bitcoin" if "Bitcoin" in url else "ChatGPT"
        return FetchResult(
            data={
                "items": [
                    {
                        "project": "en.wikipedia",
                        "article": article,
                        "granularity": "daily",
                        "timestamp": "2026111100",
                        "access": "all-access",
                        "agent": "user",
                        "views": 2947 if article == "Bitcoin" else 95134,
                    },
                    {
                        "project": "en.wikipedia",
                        "article": article,
                        "granularity": "daily",
                        "timestamp": "2026111200",
                        "access": "all-access",
                        "agent": "user",
                        "views": 3121 if article == "Bitcoin" else 56601,
                    },
                ]
            },
            url=url,
            source=source,
            fetched_at=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            raw_hash="sha256:raw-observations",
        )


def research_context(*, snapshots=None):
    rule = fixtures.rule_trend()
    rule["market_id"] = "s3b-future-research"
    rule["question"] = "FORECAST: research test"
    rule_record = {"rule_hash": "sha256:rule", "market_id": rule["market_id"], "status": "APPROVED", "rule": rule}
    return build_market_research_context(rule_record, None, snapshots or [], [])


class ResearchClient:
    def __init__(self, content):
        self.content = content
        self.model = AIModel.from_provider({"id": "z-ai/glm-5.3-flash", "is_ready": True, "supported_features": ["json_mode"]})

    def select_model(self, model_id=None):
        return self.model

    def chat_json(self, **kwargs):
        return AICompletion(
            content=self.content,
            text="{}",
            model=self.model.model_id,
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            request_id="req-research-test",
        )


class ResearchTests(unittest.TestCase):
    def test_observation_fetch_is_bounded_and_provenanced(self):
        from services.near_ai.observations import fetch_market_observations

        rule = fixtures.rule_trend()
        rule["source"]["article"] = "Bitcoin"
        rule["topics"][0]["article_title"] = "Bitcoin"
        rule["observation"]["baseline_date"] = "2026-11-16"
        rule["observation"]["target_date"] = "2026-11-23"
        snapshots = fetch_market_observations(
            {"rule": rule},
            fetcher=ResearchFetcher(),
            now=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertEqual(snapshot["window_end"], "2026-11-12")
        self.assertEqual(snapshot["window_start"], "2026-10-30")
        self.assertEqual(snapshot["source_status"], "incomplete")
        self.assertIn("2026-11-10", snapshot["missing_dates"])
        self.assertEqual(snapshot["observations"][-1]["source_id"], "wikimedia:en.wikipedia.org:Bitcoin:2026-11-12")
        self.assertNotIn("2026-11-16", {item["date"] for item in snapshot["observations"]})

    def test_research_prompt_stays_within_configured_bound(self):
        observations = []
        for day in list(range(27, 32)) + list(range(1, 11)):
            date = f"2026-10-{day:02d}" if day >= 27 else f"2026-11-{day:02d}"
            observations.append({"date": date, "timestamp": "", "views": 1000 + day, "observation_hash": "sha256:o", "raw_response_hash": "sha256:r", "retrieved_at": "2026-11-12T01:00:00Z", "source_url": "https://example.invalid/pageviews"})
        context = research_context(snapshots=[{
            "article": "Nvidia", "project": "en.wikipedia.org", "access": "all-access", "agent": "user",
            "window_start": "2026-10-27", "window_end": "2026-11-10", "retrieved_at": "2026-11-12T01:00:00Z",
            "source_status": "parsed", "missing_dates": [], "error": None, "source_url": "https://example.invalid/pageviews",
            "raw_response_hash": "sha256:r", "observations": observations,
        }])
        _, prompt = build_prompts(context)
        self.assertLessEqual(len(prompt), 20_000)

    def test_research_fallback_separates_sides_and_missing_target(self):
        context = research_context()
        self.assertTrue(context.research_fields_required)
        self.assertEqual(context.fallback.supporting_up[0].kind, "UNKNOWN")
        self.assertEqual(context.fallback.supporting_down[0].kind, "UNKNOWN")
        self.assertTrue(any("target date" in item for item in context.fallback.missing_evidence))
        draft = validate_brief_draft(context.fallback.to_dict(), context)
        self.assertEqual(draft.key_assumptions[0].kind, "FACT")

    def test_invalid_research_citation_is_rejected(self):
        context = research_context()
        content = context.fallback.to_dict()
        content["key_assumptions"][0]["evidence_refs"] = ["invented-source"]
        with self.assertRaises(BriefValidationError) as caught:
            validate_brief_draft(content, context)
        self.assertEqual(caught.exception.code, "UNKNOWN_EVIDENCE_REF")

    def test_mock_near_ai_research_success_is_structured_but_unverified(self):
        context = research_context()
        with tempfile.TemporaryDirectory() as temp:
            store = BriefStore(Path(temp) / "briefs.sqlite3")
            service = BriefService(
                config=NearAIConfig(api_key="test-key", model="z-ai/glm-5.3-flash", data_dir=temp, rate_limit_seconds=0),
                client=ResearchClient(context.fallback.to_dict()),
                store=store,
                now_fn=lambda: datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            )
            brief = service._generate(context, force=True)
            self.assertEqual(brief.generation_status, "AI_GENERATED")
            self.assertEqual(brief.inference["provider"], "near-ai")
            self.assertEqual(brief.inference["request_id"], "req-research-test")
            self.assertEqual(brief.inference["verification"]["status"], "unavailable")
            self.assertNotIn("test-key", brief.to_dict().__repr__())
            store.close()

    def test_success_metadata_is_safe_and_attestation_stays_unverified(self):
        snapshot = [{
            "article": "Nvidia",
            "project": "en.wikipedia.org",
            "access": "all-access",
            "agent": "user",
            "source_url": "https://example.invalid/pageviews",
            "window_start": "2026-11-03",
            "window_end": "2026-11-10",
            "raw_response_hash": "sha256:raw",
            "retrieved_at": "2026-11-12T01:00:00Z",
            "source_status": "parsed",
            "missing_dates": [],
            "error": None,
            "observations": [
                {"date": "2026-11-03", "timestamp": "2026110300", "views": 4743, "observation_hash": "sha256:o1", "raw_response_hash": "sha256:raw", "retrieved_at": "2026-11-12T01:00:00Z", "source_url": "https://example.invalid/pageviews"},
                {"date": "2026-11-10", "timestamp": "2026111000", "views": 123851, "observation_hash": "sha256:o2", "raw_response_hash": "sha256:raw", "retrieved_at": "2026-11-12T01:00:00Z", "source_url": "https://example.invalid/pageviews"},
            ],
        }]
        context = research_context(snapshots=snapshot)
        with tempfile.TemporaryDirectory() as temp:
            store = BriefStore(Path(temp) / "briefs.sqlite3")
            service = BriefService(
                config=NearAIConfig(api_key=None, data_dir=temp, rate_limit_seconds=0),
                client=SimpleNamespace(),
                store=store,
                now_fn=lambda: datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            )
            brief = service._generate(context, force=True)
            self.assertEqual(brief.generation_status, "NON_AI_FALLBACK")
            self.assertEqual(brief.inference["verification"]["status"], "not_applicable")
            self.assertIn("source_ids", brief.inference)
            self.assertNotIn("prompt", brief.inference)
            store.close()


if __name__ == "__main__":
    unittest.main()
