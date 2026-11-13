"""Prompt construction for grounded S5 trend briefs."""

from __future__ import annotations

import json

from .models import BriefContext, BriefType


SYSTEM_PROMPT = """You are Notch's careful research assistant.
Use ONLY the supplied evidence. Do not add outside facts, headlines, social posts,
measurements, dates, or market outcomes.

Hard rules:
1. Every number in your text must exactly match an allowed number from the input.
   Do not round, estimate, or invent numbers.
2. Every date must match an allowed date.
3. Separate FACT, INTERPRETATION, and UNKNOWN in the claim objects.
4. Every FACT or INTERPRETATION claim must cite one or more supplied evidence refs.
5. Do not claim sentiment, causality, guaranteed returns, or price direction.
6. Do not change, reinterpret, or overrule a frozen market rule or outcome.
7. For a market brief, explain the supplied deterministic resolution; never
   propose a different winner or formula.
8. For a market research brief, separate evidence supporting UP, evidence
   supporting DOWN, key assumptions, and matching historical context. If a side
   has no support, say so as UNKNOWN and cite no source. Never invent a source,
   event, price, participant, probability, or causal explanation.
9. Return JSON only, with exactly the requested keys. No markdown.

JSON shape:
{
  "headline": "short factual headline",
  "summary": "2-4 sentence explanation",
  "observed_signals": [
    {"text": "...", "kind": "FACT", "evidence_refs": ["ref_id"]}
  ],
  "notable_changes": [
    {"text": "...", "kind": "FACT", "evidence_refs": ["ref_id"]}
  ],
  "uncertainty": [
    {"text": "...", "kind": "UNKNOWN", "evidence_refs": []}
  ],
  "missing_evidence": ["..."],
  "suggested_research_questions": ["..."]
}
"""


def build_prompts(context: BriefContext) -> tuple[str, str]:
    schema = {
        "headline": "string",
        "summary": "string",
        "observed_signals": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
        "notable_changes": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
        "uncertainty": [
            {"text": "string", "kind": "UNKNOWN", "evidence_refs": []}
        ],
        "missing_evidence": ["string"],
        "suggested_research_questions": ["string"],
        "supporting_up": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
        "supporting_down": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
        "key_assumptions": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
        "historical_context": [
            {"text": "string", "kind": "FACT|INTERPRETATION|UNKNOWN", "evidence_refs": ["ref_id"]}
        ],
    }
    references = [ref.to_dict() for ref in context.evidence_references]
    if context.research_fields_required:
        references = [
            {
                "ref_id": ref["ref_id"],
                "kind": ref.get("kind"),
            }
            for ref in references
        ]
    grounding = context.prompt_payload
    if context.research_fields_required:
        grounding = {
            key: value
            for key, value in context.prompt_payload.items()
            if key not in {"source_ids", "rule_record", "brief_type", "measurement_window", "data_as_of", "market_id", "topic"}
        }
        resolution = grounding.get("resolution")
        if isinstance(resolution, dict):
            grounding["resolution"] = {
                key: resolution.get(key)
                for key in ("mode", "outcome", "text", "formula", "observation_window")
                if resolution.get(key) is not None
            }
        evidence = grounding.get("evidence")
        if isinstance(evidence, dict):
            grounding["evidence"] = {
                key: value
                for key, value in evidence.items()
                if key not in {"rule_hash", "evidence_digest", "raw_source_hashes"}
            }
    user_payload = {
        "task": "Write one evidence-grounded Trend Brief.",
        "brief_type": context.brief_type,
        "output_schema": schema,
        "allowed_numbers": sorted(context.allowed_numbers),
        "allowed_dates": sorted(context.allowed_dates),
        "evidence_references": references,
        "measurement_window": context.measurement_window,
        "data_as_of": context.data_as_of,
        "grounding": grounding,
    }
    if context.research_fields_required:
        user_payload["research_contract"] = {
            "supporting_up": "at least one claim; use UNKNOWN when supplied evidence does not support UP",
            "supporting_down": "at least one claim; use UNKNOWN when supplied evidence does not support DOWN",
            "key_assumptions": "at least one explicitly labelled assumption",
            "historical_context": "only same-topic, same-methodology historical references",
            "probability": "not requested; do not produce a calibrated probability",
        }
    if context.brief_type == BriefType.MARKET.value and context.resolution and not context.research_fields_required:
        user_payload["fixed_resolution"] = context.resolution.to_dict()
        user_payload["market_rule_constraint"] = (
            "The outcome and formula above are frozen. Explain them; do not change them."
        )
    user = json.dumps(user_payload, ensure_ascii=False, indent=2, sort_keys=True)
    return SYSTEM_PROMPT, user
