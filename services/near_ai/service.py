"""S5 brief generation service.

NEAR AI produces explanatory text only.  If the key, model, provider, or
structured output is unavailable, the service returns a deterministic,
source-only brief explicitly labeled as non-AI.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Callable

from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.models import iso_utc, now_utc, parse_iso

from .client import (
    AIModel,
    AICompletion,
    NearAIClient,
    NearAIError,
)
from .config import NearAIConfig
from .grounding import (
    GroundingError,
    build_market_context,
    build_market_research_context,
    build_radar_context,
    load_candidate,
    load_market,
)
from .models import (
    BRIEF_SCHEMA,
    BriefContext,
    BriefDraft,
    GenerationStatus,
    TrendBrief,
)
from .prompt import build_prompts
from .store import BriefStore
from .validation import BriefValidationError, validate_brief_draft


class BriefServiceError(RuntimeError):
    pass


def _completion_budget(config: NearAIConfig, model: AIModel) -> int:
    configured = max(256, int(config.max_tokens))
    try:
        provider_limit = int(model.max_output_length) if model.max_output_length else 0
    except (TypeError, ValueError):
        provider_limit = 0
    return min(configured, provider_limit) if provider_limit > 0 else configured


def _inference_status(provider: str, status: GenerationStatus) -> str:
    if provider == "near-ai" and status == GenerationStatus.AI_GENERATED:
        return "LIVE_AI_VERIFIED"
    if provider == "deterministic":
        return "DETERMINISTIC_FALLBACK"
    return "UNAVAILABLE"


class BriefService:
    def __init__(
        self,
        *,
        config: NearAIConfig,
        client: NearAIClient,
        store: BriefStore,
        now_fn: Callable[[], datetime] = now_utc,
    ) -> None:
        self.config = config
        self.client = client
        self.store = store
        self.now_fn = now_fn
        self.ai_calls = 0

    # ------------------------------------------------------------------
    # Public generation
    # ------------------------------------------------------------------
    def radar_brief(
        self,
        candidate_id: str,
        *,
        force: bool = False,
        allow_ai: bool = True,
    ) -> TrendBrief:
        candidate = load_candidate(candidate_id, self.config.radar_db)
        context = build_radar_context(candidate)
        return self._generate(context, force=force, allow_ai=allow_ai)

    def market_brief(
        self,
        market_id: str,
        *,
        force: bool = False,
        allow_ai: bool = True,
    ) -> TrendBrief:
        rule, evidence = load_market(market_id, self.config.oracle_db)
        context = build_market_context(rule, evidence)
        return self._generate(context, force=force, allow_ai=allow_ai)

    def market_brief_from_records(
        self,
        rule_record: dict[str, Any],
        evidence: dict[str, Any],
        *,
        force: bool = False,
        allow_ai: bool = False,
    ) -> TrendBrief:
        context = build_market_context(rule_record, evidence)
        return self._generate(context, force=force, allow_ai=allow_ai)

    def market_research_from_records(
        self,
        rule_record: dict[str, Any],
        evidence: dict[str, Any] | None,
        *,
        attention_snapshots: list[dict[str, Any]],
        historical_context: list[dict[str, Any]],
        force: bool = False,
        allow_ai: bool = True,
    ) -> TrendBrief:
        context = build_market_research_context(
            rule_record,
            evidence,
            attention_snapshots,
            historical_context,
        )
        return self._generate(context, force=force, allow_ai=allow_ai)

    def get(self, brief_id: str) -> TrendBrief | None:
        return self.store.get_by_id(brief_id)

    def list(self, **kwargs: Any) -> list[TrendBrief]:
        return self.store.list_briefs(**kwargs)

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------
    def _generate(
        self, context: BriefContext, *, force: bool, allow_ai: bool = True
    ) -> TrendBrief:
        initial_mode = "near-ai" if self.config.key_present else "deterministic"
        cache_key = self._cache_key(context, initial_mode)
        if not force:
            cached = self.store.get(cache_key)
            if cached is not None and not self._expired(cached):
                cached.cache_hit = True
                return cached
            if not allow_ai:
                deterministic_key = self._cache_key(context, "deterministic")
                cached = self.store.get(deterministic_key)
                if cached is not None and not self._expired(cached):
                    cached.cache_hit = True
                    return cached
        if not allow_ai:
            return self._fallback(
                context,
                self._cache_key(context, "deterministic"),
                status=GenerationStatus.NON_AI_FALLBACK,
                reason="AI generation is disabled for this read-only request",
                model_info=None,
                model_error=None,
            )

        model_info: AIModel | None = None
        model_error: str | None = None
        model_diagnostics: dict[str, Any] | None = None
        if self.config.key_present:
            try:
                model_info = self.client.select_model(self.config.model)
            except NearAIError as exc:
                model_error = str(exc)
                model_diagnostics = exc.diagnostics

        if not self.config.key_present:
            return self._fallback(
                context,
                cache_key,
                status=GenerationStatus.NON_AI_FALLBACK,
                reason="NEAR_AI_KEY is not configured; source-only fallback returned",
                model_info=None,
                model_error=None,
            )
        if model_info is None:
            return self._fallback(
                context,
                self._cache_key(context, "deterministic"),
                status=GenerationStatus.AI_UNAVAILABLE_FALLBACK,
                reason=f"NEAR AI model unavailable: {model_error or self.config.model}",
                model_info=None,
                model_error=model_error,
                model_diagnostics=model_diagnostics,
            )
        if self.ai_calls >= self.config.max_calls_per_run:
            return self._fallback(
                context,
                cache_key,
                status=GenerationStatus.AI_UNAVAILABLE_FALLBACK,
                reason="per-run NEAR AI call limit reached",
                model_info=model_info,
                model_error=None,
            )
        system_prompt, user_prompt = build_prompts(context)
        if len(user_prompt) > self.config.max_input_chars:
            return self._fallback(
                context,
                cache_key,
                status=GenerationStatus.AI_UNAVAILABLE_FALLBACK,
                reason="grounding prompt exceeds the configured input limit",
                model_info=model_info,
                model_error=None,
            )
        self.ai_calls += 1
        try:
            completion = self.client.chat_json(
                model=model_info.model_id,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                supported_features=model_info.supported_features,
                max_tokens=_completion_budget(self.config, model_info),
            )
            draft = validate_brief_draft(completion.content, context)
        except BriefValidationError as exc:
            return self._fallback(
                context,
                cache_key,
                status=GenerationStatus.INVALID_AI_FALLBACK,
                reason=f"AI output rejected: {exc.code}: {exc}",
                model_info=model_info,
                model_error=None,
            )
        except NearAIError as exc:
            return self._fallback(
                context,
                cache_key,
                status=GenerationStatus.AI_UNAVAILABLE_FALLBACK,
                reason=f"NEAR AI request failed: {exc}",
                model_info=model_info,
                model_error=str(exc),
                model_diagnostics=exc.diagnostics,
            )
        brief = self._build(
            context,
            draft,
            provider="near-ai",
            model=model_info.model_id,
            status=GenerationStatus.AI_GENERATED,
            usage={
                **completion.usage,
                "response_diagnostics": completion.diagnostics,
                "estimated_cost_usd": completion.estimated_cost_usd(model_info),
            },
            fallback_reason=None,
            request_id=completion.request_id,
        )
        brief.inference.update(
            {
                "provider_base_url": self.config.base_url,
                "response_model": completion.model,
                "model_capabilities": {
                    "supported_features": list(model_info.supported_features),
                    "max_output_length": model_info.max_output_length,
                },
                "request_parameters": {
                    "temperature": self.config.temperature,
                    "max_tokens": completion.diagnostics.get("max_tokens_requested"),
                    "response_format": completion.diagnostics.get("response_format"),
                    "attempt": completion.diagnostics.get("attempt"),
                    "max_attempts": completion.diagnostics.get("max_attempts"),
                },
            }
        )
        self.store.save(cache_key, brief)
        return brief

    def _fallback(
        self,
        context: BriefContext,
        cache_key: str,
        *,
        status: GenerationStatus,
        reason: str,
        model_info: AIModel | None,
        model_error: str | None,
        model_diagnostics: dict[str, Any] | None = None,
    ) -> TrendBrief:
        brief = self._build(
            context,
            context.fallback,
            provider="deterministic",
            model="none",
            status=status,
            usage={},
            fallback_reason=reason,
            request_id=None,
        )
        if model_info is not None:
            brief.usage["model_catalog_verified"] = True
            brief.usage["model"] = model_info.model_id
        if model_error:
            brief.usage["model_error"] = model_error
        if model_diagnostics:
            brief.usage["model_diagnostics"] = dict(model_diagnostics)
        self.store.save(cache_key, brief)
        return brief

    def _build(
        self,
        context: BriefContext,
        draft: BriefDraft,
        *,
        provider: str,
        model: str,
        status: GenerationStatus,
        usage: dict[str, Any],
        fallback_reason: str | None,
        request_id: str | None = None,
    ) -> TrendBrief:
        now = self.now_fn()
        generated_at = iso_utc(now) or ""
        brief_key = self._cache_key(context, "near-ai" if provider == "near-ai" else "deterministic")
        brief_id = "brief_" + hashlib.sha256(brief_key.encode("utf-8")).hexdigest()[:20]
        research = {
            "supporting_up": [claim.to_dict() for claim in draft.supporting_up],
            "supporting_down": [claim.to_dict() for claim in draft.supporting_down],
            "key_assumptions": [claim.to_dict() for claim in draft.key_assumptions],
            "historical_context": [claim.to_dict() for claim in draft.historical_context],
        }
        evidence_payload = context.prompt_payload.get("evidence")
        input_evidence_digest = (
            str(evidence_payload.get("evidence_digest"))
            if isinstance(evidence_payload, dict) and evidence_payload.get("evidence_digest")
            else None
        )
        inference = {
            "status": _inference_status(provider, status),
            "provider": provider,
            "model": model,
            "request_timestamp": generated_at,
            "input_observation_cutoff": context.measurement_window.get("observation_cutoff"),
            "input_digest": context.input_digest,
            "input_evidence_digest": input_evidence_digest,
            "source_ids": sorted(ref.ref_id for ref in context.evidence_references),
            "generation_status": status.value,
            "verification": {
                "status": "unavailable" if provider == "near-ai" else "not_applicable",
                "reason": (
                    "NEAR AI response signature and preflight attestation were not cryptographically verified."
                    if provider == "near-ai"
                    else "No AI inference was used."
                ),
            },
        }
        if request_id:
            inference["request_id"] = request_id
        return TrendBrief(
            schema_version=BRIEF_SCHEMA,
            brief_id=brief_id,
            brief_type=context.brief_type,
            topic=context.topic,
            candidate_id=context.candidate_id,
            market_id=context.market_id,
            headline=draft.headline,
            summary=draft.summary,
            observed_signals=draft.observed_signals,
            notable_changes=draft.notable_changes,
            evidence_references=context.evidence_references,
            measurement_window=context.measurement_window,
            data_as_of=context.data_as_of,
            uncertainty=draft.uncertainty,
            missing_evidence=draft.missing_evidence,
            suggested_research_questions=draft.suggested_research_questions,
            generated_at=generated_at,
            provider=provider,
            model=model,
            generation_status=status.value,
            resolution=context.resolution,
            fallback_reason=fallback_reason,
            usage=usage,
            input_digest=context.input_digest,
            cache_hit=False,
            research=research,
            inference=inference,
        )

    def _cache_key(self, context: BriefContext, mode: str) -> str:
        return "briefkey_" + sha256_text(
            canonical_json(
                {
                    "input_digest": context.input_digest,
                    "prompt_version": self.config.prompt_version,
                    "model": self.config.model if mode == "near-ai" else "deterministic",
                    "mode": mode,
                }
            )
        )

    def _expired(self, brief: TrendBrief) -> bool:
        generated = parse_iso(brief.generated_at)
        if generated is None:
            return True
        return generated + timedelta(seconds=self.config.cache_ttl_seconds) <= self.now_fn()

    # ------------------------------------------------------------------
    # Status / interface helpers
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": "near-ai",
            "base_url": self.config.base_url,
            "configured_model": self.config.model,
            "key_present": self.config.key_present,
            "model_verified": False,
            "catalog_count": 0,
            "model": None,
            "error": None,
            "cache_count": self.store.count(),
        }
        try:
            models = self.client.list_models()
            payload["catalog_count"] = len(models)
            selected = next((m for m in models if m.model_id == self.config.model), None)
            if selected is None:
                payload["error"] = "configured model not found in live catalog"
            elif selected.is_ready is False:
                payload["error"] = "configured model is present but not ready"
            else:
                payload["model_verified"] = True
                payload["model"] = selected.to_dict()
        except NearAIError as exc:
            payload["error"] = str(exc)
        return payload

    def brief_summary(self, brief: TrendBrief) -> dict[str, Any]:
        return {
            "brief_id": brief.brief_id,
            "inference_status": brief.inference.get("status", "UNAVAILABLE"),
            "brief_type": brief.brief_type,
            "topic": brief.topic,
            "candidate_id": brief.candidate_id,
            "market_id": brief.market_id,
            "headline": brief.headline,
            "generation_status": brief.generation_status,
            "provider": brief.provider,
            "model": brief.model,
            "generated_at": brief.generated_at,
            "cache_hit": brief.cache_hit,
            "input_digest": brief.input_digest,
            "inference": brief.inference,
        }
