"""Typed, serialisable models for Creator Studio notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NOTE_SCHEMA = "notch.creator-research-note/1"
NOTE_STATUSES = {"DRAFT", "PUBLISHED", "WITHDRAWN"}


@dataclass(frozen=True)
class CreatorResearchNote:
    note_id: str
    creator_account: str
    creator_verified: bool
    status: str
    revision: int
    title: str
    thesis: str
    reference: dict[str, Any]
    position: str
    supporting_evidence: list[dict[str, Any]]
    contradictory_evidence: list[dict[str, Any]]
    observation_cutoff: str
    source_ids: list[str]
    source_urls: list[str]
    strategy_reference: dict[str, Any] | None
    evaluation_reference: dict[str, Any] | None
    content_digest: str
    evidence_digest: str
    created_at: str
    updated_at: str
    published_at: str | None = None
    withdrawn_at: str | None = None
    withdrawal_reason: str | None = None
    premium_enabled: bool = False
    premium_body: str | None = None
    premium_body_digest: str | None = None
    premium_price_base_units: str | None = None
    premium_token_contract: str | None = None
    premium_token_symbol: str | None = None
    premium_token_decimals: int | None = None

    def premium_dict(self, *, include_body: bool) -> dict[str, Any]:
        value: dict[str, Any] = {
            "enabled": self.premium_enabled,
            "price_base_units": self.premium_price_base_units,
            "token_contract": self.premium_token_contract,
            "token_symbol": self.premium_token_symbol,
            "token_decimals": self.premium_token_decimals,
            "body_digest": self.premium_body_digest,
            "locked": self.premium_enabled and not include_body,
        }
        if include_body:
            value["body"] = self.premium_body
        return value

    def to_dict(self, *, include_premium_body: bool = True) -> dict[str, Any]:
        return {
            "schema": NOTE_SCHEMA,
            "note_id": self.note_id,
            "creator_account": self.creator_account,
            "creator_verified": self.creator_verified,
            "status": self.status,
            "revision": self.revision,
            "title": self.title,
            "thesis": self.thesis,
            "reference": self.reference,
            "position": self.position,
            "supporting_evidence": self.supporting_evidence,
            "contradictory_evidence": self.contradictory_evidence,
            "observation_cutoff": self.observation_cutoff,
            "source_ids": self.source_ids,
            "source_urls": self.source_urls,
            "strategy_reference": self.strategy_reference,
            "evaluation_reference": self.evaluation_reference,
            "content_digest": self.content_digest,
            "evidence_digest": self.evidence_digest,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "withdrawn_at": self.withdrawn_at,
            "withdrawal_reason": self.withdrawal_reason,
            "premium": self.premium_dict(include_body=include_premium_body),
        }

    def public_dict(self) -> dict[str, Any]:
        # Public notes expose the offer and provenance, never premium text.
        return self.to_dict(include_premium_body=False)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CreatorResearchNote":
        return cls(
            note_id=str(value["note_id"]),
            creator_account=str(value["creator_account"]),
            creator_verified=bool(value.get("creator_verified", False)),
            status=str(value["status"]),
            revision=int(value["revision"]),
            title=str(value["title"]),
            thesis=str(value["thesis"]),
            reference=dict(value["reference"]),
            position=str(value["position"]),
            supporting_evidence=[dict(item) for item in value.get("supporting_evidence", [])],
            contradictory_evidence=[dict(item) for item in value.get("contradictory_evidence", [])],
            observation_cutoff=str(value["observation_cutoff"]),
            source_ids=[str(item) for item in value.get("source_ids", [])],
            source_urls=[str(item) for item in value.get("source_urls", [])],
            strategy_reference=(dict(value["strategy_reference"]) if value.get("strategy_reference") else None),
            evaluation_reference=(dict(value["evaluation_reference"]) if value.get("evaluation_reference") else None),
            content_digest=str(value["content_digest"]),
            evidence_digest=str(value["evidence_digest"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            published_at=value.get("published_at"),
            withdrawn_at=value.get("withdrawn_at"),
            withdrawal_reason=value.get("withdrawal_reason"),
            premium_enabled=bool((value.get("premium") or {}).get("enabled", value.get("premium_enabled", False))),
            premium_body=(value.get("premium") or {}).get("body", value.get("premium_body")),
            premium_body_digest=(value.get("premium") or {}).get("body_digest", value.get("premium_body_digest")),
            premium_price_base_units=(value.get("premium") or {}).get("price_base_units", value.get("premium_price_base_units")),
            premium_token_contract=(value.get("premium") or {}).get("token_contract", value.get("premium_token_contract")),
            premium_token_symbol=(value.get("premium") or {}).get("token_symbol", value.get("premium_token_symbol")),
            premium_token_decimals=(
                int((value.get("premium") or {}).get("token_decimals", value.get("premium_token_decimals")))
                if (value.get("premium") or {}).get("token_decimals", value.get("premium_token_decimals")) is not None
                else None
            ),
        )

    def preview(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "creator_account": self.creator_account,
            "creator_verified": self.creator_verified,
            "status": self.status,
            "revision": self.revision,
            "title": self.title,
            "thesis": self.thesis,
            "reference": self.reference,
            "position": self.position,
            "source_ids": self.source_ids,
            "observation_cutoff": self.observation_cutoff,
            "content_digest": self.content_digest,
            "evidence_digest": self.evidence_digest,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "premium": self.premium_dict(include_body=False),
        }
