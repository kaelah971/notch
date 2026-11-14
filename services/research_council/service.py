"""Bounded Bull/Bear/Verifier research council.

The council is deliberately read-only. It builds one market evidence context,
then gives every role the same frozen snapshot. AI output is optional and is
accepted only after citation, number/date, and unsupported-claim validation.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable

from services.near_ai.client import AIModel, NearAIClient, NearAIError
from services.near_ai.config import NearAIConfig
from services.near_ai.grounding import build_market_research_context
from services.near_ai.models import BriefContext, ClaimKind, EvidenceClaim
from services.near_ai.validation import DATE_RE, NUMBER_RE
from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.models import iso_utc, now_utc, parse_iso

from .store import ResearchCouncilStore


COUNCIL_SCHEMA = "notch.research-council/1"
COUNCIL_PROMPT_VERSION = "research-council-prompt/1"
ROLE_IDS = ("bull_analyst", "bear_analyst", "evidence_verifier")
ROLE_LABELS = {
    "bull_analyst": "Bull Analyst",
    "bear_analyst": "Bear Analyst",
    "evidence_verifier": "Evidence Verifier",
}
ROLE_STANCES = {
    "bull_analyst": "UP",
    "bear_analyst": "DOWN",
    "evidence_verifier": "NEUTRAL",
}
ROLE_INSTRUCTIONS = {
    "bull_analyst": (
        "Look only for bounded evidence that supports the UP side. Include the "
        "strongest counterpoint from the same snapshot. Do not make a probability, "
        "price claim, recommendation, or causal explanation."
    ),
    "bear_analyst": (
        "Look only for bounded evidence that supports the DOWN side. Include the "
        "strongest counterpoint from the same snapshot. Do not make a probability, "
        "price claim, recommendation, or causal explanation."
    ),
    "evidence_verifier": (
        "Check whether claims can be traced to the supplied references and whether "
        "the snapshot leaves material gaps. Do not choose a winner, forecast, or "
        "add facts outside the snapshot."
    ),
}

_BANNED_RE = re.compile(
    r"(guaranteed\s+(?:return|profit)|risk[-\s]?free|will\s+definitely|"
    r"price\s+will|bullish\s+signal|bearish\s+signal|positive\s+sentiment\s+is|"
    r"calibrated\s+probability|probability\s+of)",
    re.IGNORECASE,
)
_CLAIM_KEYS = {"text", "kind", "evidence_refs"}
_ROLE_KEYS = {
    "position",
    "headline",
    "thesis",
    "claims",
    "counterpoints",
    "open_questions",
}


class ResearchCouncilError(RuntimeError):
    pass


class CouncilValidationError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


class ResearchCouncilService:
    def __init__(
        self,
        *,
        config: NearAIConfig,
        client: NearAIClient,
        store: ResearchCouncilStore,
        now_fn: Callable[[], datetime] = now_utc,
    ) -> None:
        self.config = config
        self.client = client
        self.store = store
        self.now_fn = now_fn
        self.ai_calls = 0

    def close(self) -> None:
        self.store.close()

    def get_latest(self, market_id: str) -> dict[str, Any] | None:
        return self.store.latest_for_market(market_id)

    def generate_from_records(
        self,
        rule_record: dict[str, Any],
        evidence: dict[str, Any] | None,
        *,
        attention_snapshots: list[dict[str, Any]],
        historical_context: list[dict[str, Any]],
        force: bool = False,
        allow_ai: bool = True,
    ) -> dict[str, Any]:
        context = build_market_research_context(
            rule_record,
            evidence,
            attention_snapshots,
            historical_context,
        )
        return self.generate(context, force=force, allow_ai=allow_ai)

    def generate(
        self,
        context: BriefContext,
        *,
        force: bool = False,
        allow_ai: bool = True,
    ) -> dict[str, Any]:
        snapshot = _build_snapshot(context)
        ai_requested = bool(allow_ai and self.config.key_present)
        mode = "near-ai" if ai_requested else "deterministic"
        council_key = _council_key(snapshot, mode)
        if not force:
            cached = self.store.get(council_key)
            if cached is not None and not _expired(cached, self.now_fn(), self.config.cache_ttl_seconds):
                cached = _copy_with_cache_hit(cached)
                return cached

        generated_at = iso_utc(self.now_fn()) or ""
        model_info: AIModel | None = None
        model_error: str | None = None
        model_diagnostics: dict[str, Any] = {}
        roles: dict[str, dict[str, Any]] = {}
        ai_call_triggered = False
        shared_usage: dict[str, Any] = {}
        shared_request_id: str | None = None

        if not allow_ai:
            fallback_reason = "AI generation was disabled for this read-only request"
            for role_id in ROLE_IDS:
                roles[role_id] = _fallback_role(context, role_id, snapshot, fallback_reason, generated_at)
        elif not self.config.key_present:
            fallback_reason = "NEAR_AI_KEY is not configured; deterministic evidence lens returned"
            for role_id in ROLE_IDS:
                roles[role_id] = _fallback_role(context, role_id, snapshot, fallback_reason, generated_at)
        elif self.config.max_calls_per_run <= 0:
            fallback_reason = "the configured NEAR AI per-run call limit is zero"
            for role_id in ROLE_IDS:
                roles[role_id] = _fallback_role(
                    context,
                    role_id,
                    snapshot,
                    fallback_reason,
                    generated_at,
                    status="AI_UNAVAILABLE_FALLBACK",
                )
        elif self.ai_calls >= self.config.max_calls_per_run:
            fallback_reason = "the per-run NEAR AI call limit has been reached"
            for role_id in ROLE_IDS:
                roles[role_id] = _fallback_role(
                    context,
                    role_id,
                    snapshot,
                    fallback_reason,
                    generated_at,
                    status="AI_UNAVAILABLE_FALLBACK",
                    model=self.config.model,
                )
        else:
            try:
                model_info = self.client.select_model(self.config.model)
            except NearAIError as exc:
                model_error = str(exc)
                model_diagnostics = dict(exc.diagnostics)
            if model_info is None:
                reason = f"NEAR AI model unavailable: {model_error or self.config.model}"
                for role_id in ROLE_IDS:
                    roles[role_id] = _fallback_role(
                        context,
                        role_id,
                        snapshot,
                        reason,
                        generated_at,
                        status="AI_UNAVAILABLE_FALLBACK",
                        model_error=model_error,
                        model_diagnostics=model_diagnostics,
                    )
            else:
                system_prompt, user_prompt = _build_prompts(context, snapshot)
                if len(user_prompt) > self.config.max_input_chars:
                    reason = "the bounded council snapshot exceeds the configured input limit"
                    for role_id in ROLE_IDS:
                        roles[role_id] = _fallback_role(
                            context,
                            role_id,
                            snapshot,
                            reason,
                            generated_at,
                            status="AI_UNAVAILABLE_FALLBACK",
                            model=model_info.model_id,
                        )
                else:
                    self.ai_calls += 1
                    ai_call_triggered = True
                    try:
                        completion = self.client.chat_json(
                            model=model_info.model_id,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                        )
                        shared_usage = _safe_usage(completion.usage)
                        shared_request_id = completion.request_id
                        if set(completion.content) != {"roles"}:
                            raise CouncilValidationError("UNKNOWN_FIELD", "AI council response must contain only the roles field")
                        raw_roles = completion.content.get("roles")
                        if not isinstance(raw_roles, dict):
                            raise CouncilValidationError("MISSING_ROLES", "AI council response must contain a roles object")
                        unknown_roles = set(raw_roles) - set(ROLE_IDS)
                        if unknown_roles:
                            raise CouncilValidationError("UNKNOWN_ROLE", f"AI council response contains unknown roles: {', '.join(sorted(unknown_roles))}")
                        for role_id in ROLE_IDS:
                            candidate = raw_roles.get(role_id)
                            try:
                                normalized = validate_council_role(candidate, context, role_id)
                            except CouncilValidationError as exc:
                                roles[role_id] = _fallback_role(
                                    context,
                                    role_id,
                                    snapshot,
                                    f"AI output rejected: {exc.code}: {exc}",
                                    generated_at,
                                    status="INVALID_AI_FALLBACK",
                                    model=model_info.model_id,
                                    model_error=None,
                                    model_diagnostics=completion.diagnostics,
                                )
                            else:
                                roles[role_id] = _ai_role(
                                    normalized,
                                    role_id,
                                    snapshot,
                                    generated_at,
                                    model_info.model_id,
                                    shared_usage,
                                    shared_request_id,
                                    completion.diagnostics,
                                )
                    except CouncilValidationError as exc:
                        reason = f"AI output rejected: {exc.code}: {exc}"
                        for role_id in ROLE_IDS:
                            roles[role_id] = _fallback_role(
                                context,
                                role_id,
                                snapshot,
                                reason,
                                generated_at,
                                status="INVALID_AI_FALLBACK",
                                model=model_info.model_id,
                                model_diagnostics={},
                            )
                    except NearAIError as exc:
                        reason = f"NEAR AI request failed: {exc}"
                        for role_id in ROLE_IDS:
                            roles[role_id] = _fallback_role(
                                context,
                                role_id,
                                snapshot,
                                reason,
                                generated_at,
                                status="AI_UNAVAILABLE_FALLBACK",
                                model=model_info.model_id,
                                model_error=str(exc),
                                model_diagnostics=dict(exc.diagnostics),
                            )

        role_list = [roles[role_id] for role_id in ROLE_IDS]
        disagreement = _build_disagreement(role_list)
        result_digest = "sha256:" + sha256_text(
            canonical_json(
                {
                    "snapshot_digest": snapshot["snapshot_digest"],
                    "roles": role_list,
                    "disagreement": disagreement,
                }
            )
        )
        audit = _build_audit(
            context,
            snapshot,
            role_list,
            disagreement,
            generated_at,
            result_digest,
            ai_call_triggered,
            shared_request_id,
        )
        generation_mode = _generation_mode(role_list)
        council = {
            "schema_version": COUNCIL_SCHEMA,
            "council_id": "council_" + sha256_text(council_key)[:20],
            "market_id": context.market_id,
            "topic": context.topic,
            "created_at": generated_at,
            "generation_mode": generation_mode,
            "ai_call_triggered": ai_call_triggered,
            "cache_hit": False,
            "snapshot": snapshot,
            "roles": role_list,
            "disagreement": disagreement,
            "audit": audit,
            "result_digest": result_digest,
            "limitations": [
                "All roles use one bounded evidence snapshot; no outside discovery is performed.",
                "Attention observations do not establish sentiment, causality, price direction, or a calibrated probability.",
                "This workspace is read-only and does not create a wallet action, transaction, publication, or settlement.",
            ],
            "execution": {
                "wallet_action": False,
                "signature_requested": False,
                "broadcast": False,
                "market_publication": False,
                "settlement": False,
            },
        }
        self.store.save(council_key, council)
        return council


def validate_council_role(
    content: Any,
    context: BriefContext,
    role_id: str,
) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise CouncilValidationError("NOT_OBJECT", "role output must be an object")
    extra = set(content) - _ROLE_KEYS
    if extra:
        raise CouncilValidationError("UNKNOWN_FIELD", f"unsupported role fields: {', '.join(sorted(extra))}")
    missing = _ROLE_KEYS - set(content)
    if missing:
        raise CouncilValidationError("MISSING_FIELD", f"role output is missing: {', '.join(sorted(missing))}")
    position = content.get("position")
    allowed_positions = {"UP", "DOWN", "NEUTRAL"}
    if position not in allowed_positions:
        raise CouncilValidationError("INVALID_POSITION", "position must be UP, DOWN, or NEUTRAL", field="position")
    headline = _text(content.get("headline"), "headline", 180)
    thesis = _text(content.get("thesis"), "thesis", 500)
    claims = _claims(content.get("claims"), context, "claims", min_items=1, max_items=5)
    counterpoints = _claims(content.get("counterpoints"), context, "counterpoints", min_items=1, max_items=5)
    questions = _strings(content.get("open_questions"), "open_questions", max_items=4, max_len=220)
    for text in [headline, thesis, *questions, *(claim.text for claim in claims), *(claim.text for claim in counterpoints)]:
        _validate_text(text, context)
    if role_id == "bull_analyst" and position == "DOWN":
        raise CouncilValidationError("ROLE_POSITION_MISMATCH", "Bull Analyst cannot take a DOWN position", field="position")
    if role_id == "bear_analyst" and position == "UP":
        raise CouncilValidationError("ROLE_POSITION_MISMATCH", "Bear Analyst cannot take an UP position", field="position")
    if role_id == "evidence_verifier" and position != "NEUTRAL":
        raise CouncilValidationError("ROLE_POSITION_MISMATCH", "Evidence Verifier must be NEUTRAL", field="position")
    return {
        "position": position,
        "headline": headline,
        "thesis": thesis,
        "claims": [claim.to_dict() for claim in claims],
        "counterpoints": [claim.to_dict() for claim in counterpoints],
        "open_questions": questions,
    }


def _build_snapshot(context: BriefContext) -> dict[str, Any]:
    prompt_snapshot = {
        "schema_version": "notch.research-council.snapshot/1",
        "prompt_version": COUNCIL_PROMPT_VERSION,
        "brief_type": context.brief_type,
        "market_id": context.market_id,
        "topic": context.topic,
        "measurement_window": context.measurement_window,
        "data_as_of": context.data_as_of,
        "evidence_references": [ref.to_dict() for ref in context.evidence_references],
        "grounding": context.prompt_payload,
        "allowed_numbers": sorted(context.allowed_numbers),
        "allowed_dates": sorted(context.allowed_dates),
    }
    digest = "sha256:" + sha256_text(canonical_json(prompt_snapshot))
    grounding = context.prompt_payload
    observations = grounding.get("attention_observations") if isinstance(grounding, dict) else []
    historical = grounding.get("historical_context") if isinstance(grounding, dict) else []
    return {
        "snapshot_id": "snapshot_" + digest.split(":", 1)[1][:20],
        "snapshot_digest": digest,
        "input_digest": context.input_digest,
        "market_id": context.market_id,
        "topic": context.topic,
        "data_as_of": context.data_as_of,
        "measurement_window": context.measurement_window,
        "source_ids": sorted(ref.ref_id for ref in context.evidence_references),
        "evidence_references": [ref.to_dict() for ref in context.evidence_references],
        "allowed_numbers": sorted(context.allowed_numbers),
        "allowed_dates": sorted(context.allowed_dates),
        "grounding": context.prompt_payload,
        "scope": {
            "attention_snapshot_count": len(observations) if isinstance(observations, list) else 0,
            "historical_context_count": len(historical) if isinstance(historical, list) else 0,
            "rule_locked": True,
            "outside_discovery": False,
        },
        "grounding_digest": digest,
    }


def _build_prompts(context: BriefContext, snapshot: dict[str, Any]) -> tuple[str, str]:
    system = """You are Notch's evidence-grounded Research Council.
Use only the single supplied evidence snapshot. Do not use outside knowledge,
news, prices, sentiment, causality, probabilities, recommendations, or private
reasoning. Every FACT or INTERPRETATION claim must cite supplied evidence_refs.
UNKNOWN claims must say what the snapshot does not establish and may have no refs.
Every number and date must exactly match the supplied allowed lists. Never change
the frozen rule or oracle outcome. Return JSON only with exactly this shape:
{
  "roles": {
    "bull_analyst": {"position":"UP|NEUTRAL", "headline":"...", "thesis":"...", "claims":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "counterpoints":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "open_questions":["..."]},
    "bear_analyst": {"position":"DOWN|NEUTRAL", "headline":"...", "thesis":"...", "claims":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "counterpoints":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "open_questions":["..."]},
    "evidence_verifier": {"position":"NEUTRAL", "headline":"...", "thesis":"...", "claims":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "counterpoints":[{"text":"...","kind":"FACT|INTERPRETATION|UNKNOWN","evidence_refs":["ref_id"]}], "open_questions":["..."]}
  }
}
"""
    role_instructions = {role_id: ROLE_INSTRUCTIONS[role_id] for role_id in ROLE_IDS}
    user = canonical_json(
        {
            "task": "Generate three independent research lenses over one bounded snapshot.",
            "role_instructions": role_instructions,
            "allowed_numbers": sorted(context.allowed_numbers),
            "allowed_dates": sorted(context.allowed_dates),
            "snapshot": snapshot,
        }
    )
    return system, user


def _fallback_role(
    context: BriefContext,
    role_id: str,
    snapshot: dict[str, Any],
    reason: str,
    generated_at: str,
    *,
    status: str = "NON_AI_FALLBACK",
    model: str = "none",
    model_error: str | None = None,
    model_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role_id == "bull_analyst":
        claims = list(context.fallback.supporting_up[:3])
        counterpoints = list(context.fallback.supporting_down[:2])
        position = "UP" if any(claim.kind != ClaimKind.UNKNOWN.value for claim in claims) else "NEUTRAL"
        headline = "Deterministic UP evidence lens"
        thesis = "The supplied snapshot is read for observations that could support UP; it is not a forecast."
    elif role_id == "bear_analyst":
        claims = list(context.fallback.supporting_down[:3])
        counterpoints = list(context.fallback.supporting_up[:2])
        position = "DOWN" if any(claim.kind != ClaimKind.UNKNOWN.value for claim in claims) else "NEUTRAL"
        headline = "Deterministic DOWN evidence lens"
        thesis = "The supplied snapshot is read for observations that could support DOWN; it is not a forecast."
    else:
        rule_ref = next((ref.ref_id for ref in context.evidence_references if ref.kind == "rule"), None)
        claims = [
            EvidenceClaim(
                "Citations are checked against the supplied evidence references and the published rule.",
                ClaimKind.FACT.value,
                [rule_ref] if rule_ref else [],
            )
        ]
        counterpoints = [
            EvidenceClaim(
                "The snapshot does not establish causality, sentiment, price direction, or a calibrated probability.",
                ClaimKind.UNKNOWN.value,
                [],
            )
        ]
        position = "NEUTRAL"
        headline = "Deterministic evidence verification"
        thesis = "The verifier checks source scope, citation coverage, and unresolved gaps without adding outside facts."
    if not claims:
        claims = [
            EvidenceClaim(
                f"The supplied evidence does not establish a case for {role_id.replace('_analyst', '').upper()}.",
                ClaimKind.UNKNOWN.value,
                [],
            )
        ]
    if not counterpoints:
        counterpoints = [
            EvidenceClaim(
                "The bounded snapshot does not supply an opposing cited observation.",
                ClaimKind.UNKNOWN.value,
                [],
            )
        ]
    questions = list(dict.fromkeys([*context.fallback.missing_evidence, *context.fallback.suggested_research_questions]))[:4]
    if not questions:
        questions = ["What additional source should a reviewer check before relying on this lens?"]
    normalized = {
        "position": position,
        "headline": headline,
        "thesis": thesis,
        "claims": [claim.to_dict() for claim in claims],
        "counterpoints": [claim.to_dict() for claim in counterpoints],
        "open_questions": questions,
    }
    validation = _citation_report(normalized, context)
    role = _role_record(
        normalized,
        role_id,
        snapshot,
        generated_at,
        status,
        provider="deterministic",
        model=model,
        fallback_reason=reason,
        citation_validation=validation,
        inference={
            "provider": "deterministic",
            "model": model,
            "input_digest": context.input_digest,
            "source_ids": snapshot["source_ids"],
            "generation_status": status,
            "verification": {"status": "not_applicable", "reason": "No AI inference was used."},
        },
    )
    if model_error:
        role["inference"]["model_error"] = model_error
    if model_diagnostics:
        role["inference"]["model_diagnostics"] = dict(model_diagnostics)
    return role


def _ai_role(
    normalized: dict[str, Any],
    role_id: str,
    snapshot: dict[str, Any],
    generated_at: str,
    model: str,
    usage: dict[str, Any],
    request_id: str | None,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    validation = {
        "status": "valid",
        "checked_claims": len(normalized["claims"]) + len(normalized["counterpoints"]),
        "invalid_refs": [],
        "issues": [],
    }
    inference = {
        "provider": "near-ai",
        "model": model,
        "request_timestamp": generated_at,
        "input_digest": snapshot["input_digest"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "source_ids": snapshot["source_ids"],
        "generation_status": "AI_GENERATED",
        "verification": {
            "status": "unavailable",
            "reason": "NEAR AI response signature and preflight attestation were not cryptographically verified.",
        },
        "usage": dict(usage),
        "response_diagnostics": dict(diagnostics),
    }
    if request_id:
        inference["request_id"] = request_id
    return _role_record(
        normalized,
        role_id,
        snapshot,
        generated_at,
        "AI_GENERATED",
        provider="near-ai",
        model=model,
        fallback_reason=None,
        citation_validation=validation,
        inference=inference,
    )


def _role_record(
    normalized: dict[str, Any],
    role_id: str,
    snapshot: dict[str, Any],
    generated_at: str,
    status: str,
    *,
    provider: str,
    model: str,
    fallback_reason: str | None,
    citation_validation: dict[str, Any],
    inference: dict[str, Any],
) -> dict[str, Any]:
    return {
        "role_id": role_id,
        "label": ROLE_LABELS[role_id],
        "stance": ROLE_STANCES[role_id],
        "position": normalized["position"],
        "headline": normalized["headline"],
        "thesis": normalized["thesis"],
        "claims": normalized["claims"],
        "counterpoints": normalized["counterpoints"],
        "open_questions": normalized["open_questions"],
        "generation_status": status,
        "provider": provider,
        "model": model,
        "generated_at": generated_at,
        "fallback_reason": fallback_reason,
        "snapshot_id": snapshot["snapshot_id"],
        "input_digest": snapshot["input_digest"],
        "citation_validation": citation_validation,
        "inference": inference,
    }


def _build_disagreement(roles: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {role["role_id"]: role for role in roles}
    bull_refs = _cited_refs(by_id.get("bull_analyst", {}), meaningful_only=True)
    bear_refs = _cited_refs(by_id.get("bear_analyst", {}), meaningful_only=True)
    shared = sorted(bull_refs & bear_refs)
    bull_only = sorted(bull_refs - bear_refs)
    bear_only = sorted(bear_refs - bull_refs)
    bull_support = _has_meaningful_claim(by_id.get("bull_analyst", {}))
    bear_support = _has_meaningful_claim(by_id.get("bear_analyst", {}))
    if bull_support and bear_support:
        status = "MIXED_EVIDENCE"
        summary = "Bull and Bear lenses both found cited evidence in the same snapshot; this is disagreement tracking, not a probability or recommendation."
    elif bull_support:
        status = "UP_ONLY"
        summary = "Only the Bull lens found a non-UNKNOWN cited observation in this snapshot; absence of a Bear case is not a forecast."
    elif bear_support:
        status = "DOWN_ONLY"
        summary = "Only the Bear lens found a non-UNKNOWN cited observation in this snapshot; absence of a Bull case is not a forecast."
    else:
        status = "UNRESOLVED"
        summary = "Neither directional lens found a non-UNKNOWN cited observation in this snapshot."
    records = []
    if bull_support or bear_support:
        records.append(
            {
                "kind": "opposing_lenses",
                "bull_evidence_refs": sorted(bull_refs),
                "bear_evidence_refs": sorted(bear_refs),
                "shared_evidence_refs": shared,
                "bull_only_evidence_refs": bull_only,
                "bear_only_evidence_refs": bear_only,
            }
        )
    return {
        "status": status,
        "summary": summary,
        "records": records,
        "limitations": [
            "Different cited lenses do not establish a calibrated edge.",
            "The verifier does not resolve disagreement or alter the published rule.",
        ],
    }


def _build_audit(
    context: BriefContext,
    snapshot: dict[str, Any],
    roles: list[dict[str, Any]],
    disagreement: dict[str, Any],
    generated_at: str,
    result_digest: str,
    ai_call_triggered: bool,
    request_id: str | None,
) -> dict[str, Any]:
    role_status = [
        {
            "role_id": role["role_id"],
            "generation_status": role["generation_status"],
            "provider": role["provider"],
            "citation_status": role["citation_validation"]["status"],
        }
        for role in roles
    ]
    audit_seed = {
        "market_id": context.market_id,
        "snapshot_digest": snapshot["snapshot_digest"],
        "result_digest": result_digest,
        "created_at": generated_at,
    }
    return {
        "audit_id": "audit_" + sha256_text(canonical_json(audit_seed))[:20],
        "event": "RESEARCH_COUNCIL_GENERATED",
        "market_id": context.market_id,
        "occurred_at": generated_at,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "input_digest": context.input_digest,
        "source_ids": snapshot["source_ids"],
        "roles": role_status,
        "disagreement_status": disagreement["status"],
        "ai_call_triggered": ai_call_triggered,
        "request_id": request_id,
        "result_digest": result_digest,
        "execution_boundary": {
            "wallet_action": False,
            "signature_requested": False,
            "broadcast": False,
            "market_publication": False,
            "settlement": False,
        },
    }


def _citation_report(content: dict[str, Any], context: BriefContext) -> dict[str, Any]:
    allowed = context.reference_ids()
    checked = 0
    invalid: list[str] = []
    issues: list[str] = []
    for field in ("claims", "counterpoints"):
        for claim in content.get(field, []):
            checked += 1
            refs = claim.get("evidence_refs") or []
            invalid.extend(ref for ref in refs if ref not in allowed)
            if claim.get("kind") in {ClaimKind.FACT.value, ClaimKind.INTERPRETATION.value} and not refs:
                issues.append(f"{field} claim is missing a citation")
    if invalid:
        issues.append("one or more citations are not in the supplied snapshot")
    return {
        "status": "valid" if not invalid and not issues else "invalid",
        "checked_claims": checked,
        "invalid_refs": sorted(set(invalid)),
        "issues": issues,
    }


def _cited_refs(role: dict[str, Any], *, meaningful_only: bool) -> set[str]:
    refs: set[str] = set()
    for claim in role.get("claims") or []:
        if meaningful_only and claim.get("kind") == ClaimKind.UNKNOWN.value:
            continue
        refs.update(str(ref) for ref in claim.get("evidence_refs") or [])
    return refs


def _has_meaningful_claim(role: dict[str, Any]) -> bool:
    return any(
        claim.get("kind") in {ClaimKind.FACT.value, ClaimKind.INTERPRETATION.value}
        and bool(claim.get("evidence_refs"))
        for claim in role.get("claims") or []
    )


def _generation_mode(roles: list[dict[str, Any]]) -> str:
    statuses = {role["generation_status"] for role in roles}
    if statuses == {"AI_GENERATED"}:
        return "AI_GENERATED"
    if statuses == {"NON_AI_FALLBACK"}:
        return "DETERMINISTIC_EVIDENCE_LENSES"
    if statuses == {"AI_UNAVAILABLE_FALLBACK"}:
        return "AI_UNAVAILABLE_FALLBACK"
    if statuses == {"INVALID_AI_FALLBACK"}:
        return "INVALID_AI_FALLBACK"
    return "MIXED_AI_AND_FALLBACK"


def _council_key(snapshot: dict[str, Any], mode: str) -> str:
    return "councilkey_" + sha256_text(
        canonical_json(
            {
                "schema": COUNCIL_SCHEMA,
                "prompt_version": COUNCIL_PROMPT_VERSION,
                "snapshot_digest": snapshot["snapshot_digest"],
                "mode": mode,
            }
        )
    )


def _copy_with_cache_hit(council: dict[str, Any]) -> dict[str, Any]:
    copy = dict(council)
    copy["cache_hit"] = True
    return copy


def _expired(council: dict[str, Any], now: datetime, ttl_seconds: int) -> bool:
    if ttl_seconds <= 0:
        return False
    created = parse_iso(council.get("created_at"))
    return created is None or created + timedelta(seconds=ttl_seconds) <= now


def _text(value: Any, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CouncilValidationError("INVALID_TEXT", f"{field} must be a non-empty string", field=field)
    text = value.strip()
    if len(text) > max_len:
        raise CouncilValidationError("TEXT_TOO_LONG", f"{field} exceeds {max_len} characters", field=field)
    return text


def _strings(value: Any, field: str, *, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        raise CouncilValidationError("INVALID_LIST", f"{field} must be a list", field=field)
    if not 1 <= len(value) <= max_items:
        raise CouncilValidationError("INVALID_COUNT", f"{field} must contain 1-{max_items} items", field=field)
    return [_text(item, field, max_len) for item in value]


def _claims(
    value: Any,
    context: BriefContext,
    field: str,
    *,
    min_items: int,
    max_items: int,
) -> list[EvidenceClaim]:
    if not isinstance(value, list) or not min_items <= len(value) <= max_items:
        raise CouncilValidationError("INVALID_COUNT", f"{field} must contain {min_items}-{max_items} items", field=field)
    allowed = context.reference_ids()
    result: list[EvidenceClaim] = []
    for item in value:
        if not isinstance(item, dict) or set(item) - _CLAIM_KEYS:
            raise CouncilValidationError("INVALID_CLAIM", f"{field} entries must contain text, kind, and evidence_refs", field=field)
        text = _text(item.get("text"), field, 320)
        kind = str(item.get("kind") or "")
        if kind not in {member.value for member in ClaimKind}:
            raise CouncilValidationError("INVALID_KIND", f"{field} kind must be FACT, INTERPRETATION, or UNKNOWN", field=field)
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise CouncilValidationError("INVALID_REFS", f"{field} evidence_refs must be a string list", field=field)
        unknown = [ref for ref in refs if ref not in allowed]
        if unknown:
            raise CouncilValidationError("UNKNOWN_EVIDENCE_REF", f"{field} references unknown evidence: {', '.join(unknown)}", field=field)
        if kind in {ClaimKind.FACT.value, ClaimKind.INTERPRETATION.value} and not refs:
            raise CouncilValidationError("MISSING_EVIDENCE_REF", f"{field} {kind} claims require a citation", field=field)
        result.append(EvidenceClaim(text=text, kind=kind, evidence_refs=list(refs)))
    return result


def _validate_text(text: str, context: BriefContext) -> None:
    if _BANNED_RE.search(text):
        raise CouncilValidationError("UNSUPPORTED_CLAIM", "role output contains a banned certainty, sentiment, price, or probability claim")
    for date in DATE_RE.findall(text):
        if date not in context.allowed_dates:
            raise CouncilValidationError("UNSUPPORTED_DATE", f"date {date} is not in the supplied snapshot")
    without_dates = DATE_RE.sub(" ", text)
    for token in NUMBER_RE.findall(without_dates):
        if token.replace(",", "") not in context.allowed_numbers:
            raise CouncilValidationError("UNSUPPORTED_NUMBER", f"number {token} is not in the supplied snapshot")


def _safe_usage(usage: dict[str, Any] | None) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
        value = (usage or {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = value
    return result
