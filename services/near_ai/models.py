"""Typed S5 trend briefs and grounding context.

AI output is explanatory only.  The frozen S3B rule/evidence remains the sole
source of settlement facts and outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


BRIEF_SCHEMA = "notch.near-ai.brief/1"
PROMPT_VERSION = "s5-brief-prompt/1"


class BriefType(str, Enum):
    RADAR = "radar"
    MARKET = "market"


class ClaimKind(str, Enum):
    FACT = "FACT"
    INTERPRETATION = "INTERPRETATION"
    UNKNOWN = "UNKNOWN"


class GenerationStatus(str, Enum):
    AI_GENERATED = "AI_GENERATED"
    NON_AI_FALLBACK = "NON_AI_FALLBACK"
    INVALID_AI_FALLBACK = "INVALID_AI_FALLBACK"
    AI_UNAVAILABLE_FALLBACK = "AI_UNAVAILABLE_FALLBACK"


@dataclass(frozen=True)
class EvidenceReference:
    ref_id: str
    source: str
    title: str
    url: str | None
    observed_at: str | None
    raw_hash: str | None = None
    kind: str = "measurement"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "observed_at": self.observed_at,
            "raw_hash": self.raw_hash,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class EvidenceClaim:
    text: str
    kind: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kind": self.kind,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class ResolutionExplanation:
    rule_hash: str
    evidence_digest: str
    mode: str
    outcome: str
    text: str
    formula: str
    observation_window: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_hash": self.rule_hash,
            "evidence_digest": self.evidence_digest,
            "mode": self.mode,
            "outcome": self.outcome,
            "text": self.text,
            "formula": self.formula,
            "observation_window": self.observation_window,
        }


@dataclass(frozen=True)
class BriefDraft:
    headline: str
    summary: str
    observed_signals: list[EvidenceClaim]
    notable_changes: list[EvidenceClaim]
    uncertainty: list[EvidenceClaim]
    missing_evidence: list[str]
    suggested_research_questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "observed_signals": [c.to_dict() for c in self.observed_signals],
            "notable_changes": [c.to_dict() for c in self.notable_changes],
            "uncertainty": [c.to_dict() for c in self.uncertainty],
            "missing_evidence": list(self.missing_evidence),
            "suggested_research_questions": list(self.suggested_research_questions),
        }


@dataclass(frozen=True)
class BriefContext:
    brief_type: str
    topic: str
    candidate_id: str | None
    market_id: str | None
    measurement_window: dict[str, Any]
    data_as_of: str
    evidence_references: list[EvidenceReference]
    allowed_numbers: set[str]
    allowed_dates: set[str]
    prompt_payload: dict[str, Any]
    fallback: BriefDraft
    resolution: ResolutionExplanation | None = None
    input_digest: str = ""

    def reference_ids(self) -> set[str]:
        return {ref.ref_id for ref in self.evidence_references}

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_type": self.brief_type,
            "topic": self.topic,
            "candidate_id": self.candidate_id,
            "market_id": self.market_id,
            "measurement_window": self.measurement_window,
            "data_as_of": self.data_as_of,
            "evidence_references": [ref.to_dict() for ref in self.evidence_references],
            "allowed_numbers": sorted(self.allowed_numbers),
            "allowed_dates": sorted(self.allowed_dates),
            "prompt_payload": self.prompt_payload,
            "fallback": self.fallback.to_dict(),
            "resolution": self.resolution.to_dict() if self.resolution else None,
            "input_digest": self.input_digest,
        }


@dataclass
class TrendBrief:
    schema_version: str
    brief_id: str
    brief_type: str
    topic: str
    candidate_id: str | None
    market_id: str | None
    headline: str
    summary: str
    observed_signals: list[EvidenceClaim]
    notable_changes: list[EvidenceClaim]
    evidence_references: list[EvidenceReference]
    measurement_window: dict[str, Any]
    data_as_of: str
    uncertainty: list[EvidenceClaim]
    missing_evidence: list[str]
    suggested_research_questions: list[str]
    generated_at: str
    provider: str
    model: str
    generation_status: str
    resolution: ResolutionExplanation | None = None
    fallback_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    input_digest: str = ""
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "brief_id": self.brief_id,
            "brief_type": self.brief_type,
            "topic": self.topic,
            "candidate_id": self.candidate_id,
            "market_id": self.market_id,
            "headline": self.headline,
            "summary": self.summary,
            "observed_signals": [c.to_dict() for c in self.observed_signals],
            "notable_changes": [c.to_dict() for c in self.notable_changes],
            "evidence_references": [r.to_dict() for r in self.evidence_references],
            "measurement_window": self.measurement_window,
            "data_as_of": self.data_as_of,
            "uncertainty": [c.to_dict() for c in self.uncertainty],
            "missing_evidence": list(self.missing_evidence),
            "suggested_research_questions": list(self.suggested_research_questions),
            "generated_at": self.generated_at,
            "provider": self.provider,
            "model": self.model,
            "generation_status": self.generation_status,
            "resolution": self.resolution.to_dict() if self.resolution else None,
            "fallback_reason": self.fallback_reason,
            "usage": self.usage,
            "input_digest": self.input_digest,
            "cache_hit": self.cache_hit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrendBrief":
        def claims(key: str) -> list[EvidenceClaim]:
            return [
                EvidenceClaim(
                    text=str(item["text"]),
                    kind=str(item["kind"]),
                    evidence_refs=list(item.get("evidence_refs") or []),
                )
                for item in data.get(key, [])
            ]

        resolution = data.get("resolution")
        return cls(
            schema_version=str(data.get("schema_version") or BRIEF_SCHEMA),
            brief_id=str(data["brief_id"]),
            brief_type=str(data["brief_type"]),
            topic=str(data["topic"]),
            candidate_id=data.get("candidate_id"),
            market_id=data.get("market_id"),
            headline=str(data["headline"]),
            summary=str(data["summary"]),
            observed_signals=claims("observed_signals"),
            notable_changes=claims("notable_changes"),
            evidence_references=[
                EvidenceReference(
                    ref_id=str(item["ref_id"]),
                    source=str(item["source"]),
                    title=str(item["title"]),
                    url=item.get("url"),
                    observed_at=item.get("observed_at"),
                    raw_hash=item.get("raw_hash"),
                    kind=str(item.get("kind") or "measurement"),
                )
                for item in data.get("evidence_references", [])
            ],
            measurement_window=dict(data.get("measurement_window") or {}),
            data_as_of=str(data.get("data_as_of") or ""),
            uncertainty=claims("uncertainty"),
            missing_evidence=list(data.get("missing_evidence") or []),
            suggested_research_questions=list(data.get("suggested_research_questions") or []),
            generated_at=str(data["generated_at"]),
            provider=str(data["provider"]),
            model=str(data["model"]),
            generation_status=str(data["generation_status"]),
            resolution=(
                ResolutionExplanation(
                    rule_hash=str(resolution["rule_hash"]),
                    evidence_digest=str(resolution["evidence_digest"]),
                    mode=str(resolution["mode"]),
                    outcome=str(resolution["outcome"]),
                    text=str(resolution["text"]),
                    formula=str(resolution["formula"]),
                    observation_window=dict(resolution.get("observation_window") or {}),
                )
                if isinstance(resolution, dict)
                else None
            ),
            fallback_reason=data.get("fallback_reason"),
            usage=dict(data.get("usage") or {}),
            input_digest=str(data.get("input_digest") or ""),
            cache_hit=bool(data.get("cache_hit", False)),
        )
