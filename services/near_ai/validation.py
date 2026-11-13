"""Validation of structured AI briefs against grounded evidence.

Any numeric token in model text must match a number supplied in the context.
Unsupported numbers, unknown evidence references, invented fields, and
settlement-changing language invalidate the AI draft.
"""

from __future__ import annotations

import re
from typing import Any

from .models import BriefContext, BriefDraft, ClaimKind, EvidenceClaim


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"(?<![\w])(-?\d[\d,]*(?:\.\d+)?)")
BANNED_RE = re.compile(
    r"(guaranteed\s+(?:return|profit)|risk[-\s]?free|will\s+definitely|"
    r"price\s+will|bullish\s+signal|bearish\s+signal|positive\s+sentiment\s+is)",
    re.IGNORECASE,
)
ALLOWED_KEYS = {
    "headline",
    "summary",
    "observed_signals",
    "notable_changes",
    "uncertainty",
    "missing_evidence",
    "suggested_research_questions",
    "supporting_up",
    "supporting_down",
    "key_assumptions",
    "historical_context",
}
RESEARCH_KEYS = {"supporting_up", "supporting_down", "key_assumptions", "historical_context"}
CLAIM_KEYS = {"text", "kind", "evidence_refs"}


class BriefValidationError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "field": self.field}


def validate_brief_draft(content: dict[str, Any], context: BriefContext) -> BriefDraft:
    if not isinstance(content, dict):
        raise BriefValidationError("NOT_OBJECT", "brief must be a JSON object")
    extra = set(content) - ALLOWED_KEYS
    if extra:
        raise BriefValidationError(
            "UNKNOWN_FIELD",
            f"unsupported AI fields: {', '.join(sorted(extra))}",
        )
    required = {
        "headline",
        "summary",
        "observed_signals",
        "notable_changes",
        "uncertainty",
        "missing_evidence",
        "suggested_research_questions",
    }
    if context.research_fields_required:
        required |= RESEARCH_KEYS
    missing = required - set(content)
    if missing:
        raise BriefValidationError(
            "MISSING_FIELD",
            f"missing AI fields: {', '.join(sorted(missing))}",
        )
    headline = _text(content["headline"], "headline", 180)
    summary = _text(content["summary"], "summary", 700)
    observed = _claims(content["observed_signals"], context, "observed_signals", min_items=0 if context.research_fields_required else 1, max_items=5)
    notable = _claims(content["notable_changes"], context, "notable_changes", min_items=0, max_items=5)
    uncertainty = _claims(content["uncertainty"], context, "uncertainty", min_items=1, max_items=5)
    missing_evidence = _string_list(content["missing_evidence"], "missing_evidence", max_items=5, max_len=220)
    questions = _string_list(
        content["suggested_research_questions"],
        "suggested_research_questions",
        max_items=4,
        max_len=220,
    )
    supporting_up = _claims(content.get("supporting_up", []), context, "supporting_up", min_items=1 if context.research_fields_required else 0, max_items=5)
    supporting_down = _claims(content.get("supporting_down", []), context, "supporting_down", min_items=1 if context.research_fields_required else 0, max_items=5)
    assumptions = _claims(content.get("key_assumptions", []), context, "key_assumptions", min_items=1 if context.research_fields_required else 0, max_items=5)
    historical = _claims(content.get("historical_context", []), context, "historical_context", min_items=0, max_items=5)
    texts = [headline, summary]
    texts.extend(claim.text for claim in observed)
    texts.extend(claim.text for claim in notable)
    texts.extend(claim.text for claim in uncertainty)
    texts.extend(missing_evidence)
    texts.extend(questions)
    texts.extend(claim.text for claim in supporting_up)
    texts.extend(claim.text for claim in supporting_down)
    texts.extend(claim.text for claim in assumptions)
    texts.extend(claim.text for claim in historical)
    for text in texts:
        _validate_text(text, context)
    return BriefDraft(
        headline=headline,
        summary=summary,
        observed_signals=observed,
        notable_changes=notable,
        uncertainty=uncertainty,
        missing_evidence=missing_evidence,
        suggested_research_questions=questions,
        supporting_up=supporting_up,
        supporting_down=supporting_down,
        key_assumptions=assumptions,
        historical_context=historical,
    )


def _text(value: Any, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BriefValidationError("INVALID_TEXT", f"{field} must be a non-empty string", field=field)
    text = value.strip()
    if len(text) > max_len:
        raise BriefValidationError(
            "TEXT_TOO_LONG", f"{field} exceeds {max_len} characters", field=field
        )
    return text


def _string_list(value: Any, field: str, *, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        raise BriefValidationError("INVALID_LIST", f"{field} must be a list", field=field)
    if len(value) > max_items:
        raise BriefValidationError("TOO_MANY_ITEMS", f"{field} has too many items", field=field)
    out = []
    for item in value:
        out.append(_text(item, field, max_len))
    return out


def _claims(
    value: Any,
    context: BriefContext,
    field: str,
    *,
    min_items: int,
    max_items: int,
) -> list[EvidenceClaim]:
    if not isinstance(value, list):
        raise BriefValidationError("INVALID_LIST", f"{field} must be a list", field=field)
    if not (min_items <= len(value) <= max_items):
        raise BriefValidationError(
            "INVALID_COUNT",
            f"{field} must contain {min_items}-{max_items} items",
            field=field,
        )
    allowed_refs = context.reference_ids()
    out: list[EvidenceClaim] = []
    for item in value:
        if not isinstance(item, dict):
            raise BriefValidationError("INVALID_CLAIM", f"{field} entries must be objects", field=field)
        extra = set(item) - CLAIM_KEYS
        if extra:
            raise BriefValidationError(
                "UNKNOWN_CLAIM_FIELD",
                f"{field} contains unsupported claim fields: {', '.join(sorted(extra))}",
                field=field,
            )
        text = _text(item.get("text"), field, 300)
        kind = str(item.get("kind") or "")
        if kind not in {member.value for member in ClaimKind}:
            raise BriefValidationError(
                "INVALID_KIND",
                f"{field} kind must be FACT, INTERPRETATION or UNKNOWN",
                field=field,
            )
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise BriefValidationError(
                "INVALID_REFS",
                f"{field} evidence_refs must be a string list",
                field=field,
            )
        unknown = [ref for ref in refs if ref not in allowed_refs]
        if unknown:
            raise BriefValidationError(
                "UNKNOWN_EVIDENCE_REF",
                f"{field} references unknown evidence: {', '.join(unknown)}",
                field=field,
            )
        if kind in {ClaimKind.FACT.value, ClaimKind.INTERPRETATION.value} and not refs:
            raise BriefValidationError(
                "MISSING_EVIDENCE_REF",
                f"{field} {kind} claims require at least one evidence reference",
                field=field,
            )
        out.append(EvidenceClaim(text=text, kind=kind, evidence_refs=list(refs)))
    return out


def _validate_text(text: str, context: BriefContext) -> None:
    if BANNED_RE.search(text):
        raise BriefValidationError(
            "UNSUPPORTED_CLAIM",
            "brief contains a banned certainty, sentiment or return claim",
        )
    for date in DATE_RE.findall(text):
        if date not in context.allowed_dates:
            raise BriefValidationError(
                "UNSUPPORTED_DATE",
                f"date {date} is not present in the supplied evidence",
            )
    without_dates = DATE_RE.sub(" ", text)
    for token in NUMBER_RE.findall(without_dates):
        normalized = token.replace(",", "")
        if normalized not in context.allowed_numbers:
            raise BriefValidationError(
                "UNSUPPORTED_NUMBER",
                f"number {token} is not present in the supplied evidence",
            )


def extract_numbers(text: str) -> tuple[set[str], set[str]]:
    dates = set(DATE_RE.findall(text))
    without_dates = DATE_RE.sub(" ", text)
    numbers = {token.replace(",", "") for token in NUMBER_RE.findall(without_dates)}
    return numbers, dates
