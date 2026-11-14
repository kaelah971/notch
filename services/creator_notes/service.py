"""Validation and lifecycle rules for verifiable creator research notes."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from services.intents.balance import NearRpcClient
from services.intents.validation import is_near_account
from services.trend_radar.canonical import canonical_json, normalize_name
from services.trend_radar.models import iso_utc, now_utc, parse_iso

from .identity import CreatorIdentityError, CreatorIdentityService
from .models import CreatorResearchNote
from .store import CreatorNotesStore, CreatorNotesStoreError


class CreatorNotesError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details


# Phase 8A deliberately publishes only genuine stored Wikimedia observations.
# Other Radar/market sources remain outside this V1 publication boundary.
_SOURCE_PREFIXES = ("wikimedia:",)
_SOURCE_IDS = {"wikimedia-pageviews-v1"}
_POSITIONS = {"UP", "DOWN", "NEUTRAL"}
_REFERENCE_KINDS = {"market", "topic"}
_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{16,128}$")
_WIKIMEDIA_HOSTS = {"pageviews.wmcloud.org", "wikimedia.org"}


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_parse_iso(value: str | None) -> datetime | None:
    try:
        return parse_iso(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any, field: str, *, max_length: int, required: bool = True) -> str:
    if not isinstance(value, str):
        if required:
            raise CreatorNotesError("INVALID_NOTE", f"{field} must be a string", details={"field": field})
        return ""
    value = value.strip()
    if required and not value:
        raise CreatorNotesError("INVALID_NOTE", f"{field} is required", details={"field": field})
    if len(value) > max_length:
        raise CreatorNotesError(
            "INVALID_NOTE",
            f"{field} exceeds {max_length} characters",
            details={"field": field, "max_length": max_length},
        )
    return value


def _source_id(value: Any, field: str) -> str:
    value = _clean_text(value, field, max_length=160)
    if value not in _SOURCE_IDS and not value.startswith(_SOURCE_PREFIXES):
        raise CreatorNotesError(
            "UNSUPPORTED_SOURCE",
            f"{field} is not in the supported source catalog",
            details={"field": field, "source_id": value},
        )
    return value


def _https_url(value: Any, field: str) -> str:
    value = _clean_text(value, field, max_length=1000)
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or not (
        host in _WIKIMEDIA_HOSTS
        or host.endswith(".wikimedia.org")
        or host.endswith(".wikipedia.org")
    ):
        raise CreatorNotesError(
            "INVALID_SOURCE_URL",
            f"{field} must be an HTTPS Wikimedia URL",
            details={"field": field},
        )
    return value


class CreatorNotesService:
    def __init__(
        self,
        *,
        store: CreatorNotesStore,
        reader: NearRpcClient,
        chain: Any,
        radar: Any,
        identity: CreatorIdentityService | None = None,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.store = store
        self.reader = reader
        self.chain = chain
        self.radar = radar
        self.clock = clock
        self.identity = identity or CreatorIdentityService(store=store, reader=reader, clock=clock)

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def challenge(self, account_id: str) -> dict[str, Any]:
        return self.identity.create_challenge(account_id)

    def verify_identity(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.identity.verify(
                challenge_id=str(body.get("challenge_id") or ""),
                account_id=str(body.get("account_id") or ""),
                public_key=str(body.get("public_key") or ""),
                signature=str(body.get("signature") or ""),
            )
        except CreatorIdentityError:
            raise
        return result

    def _session(self, token: str | None) -> dict[str, Any]:
        try:
            return self.identity.session(token)
        except CreatorIdentityError as exc:
            raise CreatorNotesError(exc.code, str(exc), status=exc.status) from exc

    # ------------------------------------------------------------------
    # Note validation and lifecycle
    # ------------------------------------------------------------------
    def create_draft(self, token: str | None, payload: dict[str, Any]) -> CreatorResearchNote:
        session = self._session(token)
        note = self._note_from_payload(
            payload,
            creator_account=session["account_id"],
            note_id=f"note_{uuid.uuid4().hex}",
            revision=1,
            created_at=self._now_iso(),
            updated_at=self._now_iso(),
            status="DRAFT",
            existing=None,
        )
        try:
            return self.store.create_note(note)
        except CreatorNotesStoreError as exc:
            raise CreatorNotesError("DUPLICATE_NOTE", str(exc), status=409) from exc

    def update(self, token: str | None, note_id: str, payload: dict[str, Any]) -> CreatorResearchNote:
        session = self._session(token)
        current = self._owned_note(session, note_id)
        if current.status == "WITHDRAWN":
            raise CreatorNotesError("NOTE_WITHDRAWN", "a withdrawn note cannot be edited", status=409)
        merged = current.to_dict()
        merged.update(payload)
        # These fields are identity/provenance anchors and cannot be silently replaced.
        merged["reference"] = payload.get("reference", current.reference)
        merged["strategy_reference"] = payload.get("strategy_reference", current.strategy_reference)
        merged["evaluation_reference"] = payload.get("evaluation_reference", current.evaluation_reference)
        now = self._now_iso()
        note = self._note_from_payload(
            merged,
            creator_account=session["account_id"],
            note_id=current.note_id,
            revision=current.revision + 1,
            created_at=current.created_at,
            updated_at=now,
            status="DRAFT",
            existing=current,
        )
        try:
            return self.store.save_revision(note)
        except CreatorNotesStoreError as exc:
            raise CreatorNotesError("DUPLICATE_NOTE", str(exc), status=409) from exc

    def publish(self, token: str | None, note_id: str) -> CreatorResearchNote:
        session = self._session(token)
        current = self._owned_note(session, note_id)
        if current.status == "PUBLISHED":
            raise CreatorNotesError("ALREADY_PUBLISHED", "note is already published", status=409)
        if current.status == "WITHDRAWN":
            raise CreatorNotesError("NOTE_WITHDRAWN", "a withdrawn note cannot be republished", status=409)
        self._publication_validate(current)
        duplicate = self.store.find_published_digest(current.creator_account, current.content_digest)
        if duplicate is not None:
            raise CreatorNotesError(
                "DUPLICATE_PUBLICATION",
                "this creator has already published the same note revision",
                status=409,
                details={"note_id": duplicate.note_id},
            )
        now = self._now_iso()
        published = CreatorResearchNote(
            **{
                **current.__dict__,
                "status": "PUBLISHED",
                "revision": current.revision + 1,
                "updated_at": now,
                "published_at": now,
                "withdrawn_at": None,
                "withdrawal_reason": None,
            }
        )
        try:
            return self.store.save_revision(published)
        except CreatorNotesStoreError as exc:
            raise CreatorNotesError("DUPLICATE_PUBLICATION", str(exc), status=409) from exc

    def withdraw(self, token: str | None, note_id: str, reason: str | None = None) -> CreatorResearchNote:
        session = self._session(token)
        current = self._owned_note(session, note_id)
        if current.status == "WITHDRAWN":
            return current
        now = self._now_iso()
        withdrawn = CreatorResearchNote(
            **{
                **current.__dict__,
                "status": "WITHDRAWN",
                "revision": current.revision + 1,
                "updated_at": now,
                "withdrawn_at": now,
                "withdrawal_reason": _clean_text(reason or "Withdrawn by creator", "reason", max_length=500),
            }
        )
        return self.store.save_revision(withdrawn)

    def mine(self, token: str | None, limit: int = 20) -> list[dict[str, Any]]:
        session = self._session(token)
        return [self._with_history(note, private=True) for note in self.store.list_notes(creator_account=session["account_id"], limit=limit)]

    def public_list(self, limit: int = 20) -> list[dict[str, Any]]:
        return [note.preview() for note in self.store.list_notes(status="PUBLISHED", limit=limit)]

    def public_detail(self, note_id: str) -> dict[str, Any]:
        note = self.store.get_note(note_id)
        if note is None or note.status != "PUBLISHED":
            raise CreatorNotesError("NOTE_NOT_FOUND", "published research note was not found", status=404)
        return self._with_history(note, private=False)

    def creator_public(self, account_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not is_near_account(account_id):
            raise CreatorNotesError("INVALID_ACCOUNT", "account_id is not a valid NEAR account")
        return [note.preview() for note in self.store.list_notes(status="PUBLISHED", creator_account=account_id, limit=limit)]

    def _owned_note(self, session: dict[str, Any], note_id: str) -> CreatorResearchNote:
        note = self.store.get_note(note_id)
        if note is None:
            raise CreatorNotesError("NOTE_NOT_FOUND", "research note was not found", status=404)
        if note.creator_account != session["account_id"]:
            raise CreatorNotesError("NOTE_FORBIDDEN", "only the verified creator can edit this note", status=403)
        return note

    def _publication_validate(self, note: CreatorResearchNote) -> None:
        if not note.creator_verified:
            raise CreatorNotesError("IDENTITY_REQUIRED", "a note must be owned by a verified wallet before publication", status=403)
        if not note.supporting_evidence:
            raise CreatorNotesError("EVIDENCE_REQUIRED", "publication requires at least one supporting source-backed observation")
        cutoff = _safe_parse_iso(note.observation_cutoff)
        current = self.clock()
        if cutoff is None:
            raise CreatorNotesError("INVALID_CUTOFF", "observation_cutoff must be an ISO-8601 timestamp")
        if cutoff > current.astimezone(timezone.utc):
            raise CreatorNotesError("LOOKAHEAD_BLOCKED", "observation_cutoff cannot be in the future")
        if not note.source_ids:
            raise CreatorNotesError("SOURCE_REQUIRED", "publication requires at least one validated source")
        if note.reference.get("kind") not in _REFERENCE_KINDS:
            raise CreatorNotesError("INVALID_REFERENCE", "publication requires a market or research topic reference")

    def _note_from_payload(
        self,
        payload: dict[str, Any],
        *,
        creator_account: str,
        note_id: str,
        revision: int,
        created_at: str,
        updated_at: str,
        status: str,
        existing: CreatorResearchNote | None,
    ) -> CreatorResearchNote:
        title = _clean_text(payload.get("title"), "title", max_length=140)
        thesis = _clean_text(payload.get("thesis"), "thesis", max_length=4000)
        position = _clean_text(payload.get("position", ""), "position", max_length=20).upper()
        if position not in _POSITIONS:
            raise CreatorNotesError("INVALID_POSITION", "position must be UP, DOWN, or NEUTRAL")
        reference = self._reference(payload.get("reference"))
        cutoff = _clean_text(payload.get("observation_cutoff"), "observation_cutoff", max_length=80)
        parsed_cutoff = _safe_parse_iso(cutoff)
        if parsed_cutoff is None:
            raise CreatorNotesError("INVALID_CUTOFF", "observation_cutoff must be an ISO-8601 timestamp")
        if parsed_cutoff > self.clock().astimezone(timezone.utc):
            raise CreatorNotesError("LOOKAHEAD_BLOCKED", "observation_cutoff cannot be in the future")
        supporting = self._evidence(payload.get("supporting_evidence", []), "supporting_evidence", cutoff, reference)
        contradictory = self._evidence(payload.get("contradictory_evidence", []), "contradictory_evidence", cutoff, reference)
        if len(supporting) > 8 or len(contradictory) > 8:
            raise CreatorNotesError("TOO_MANY_EVIDENCE_ITEMS", "each evidence lane may contain at most 8 items")
        all_evidence = supporting + contradictory
        source_ids = sorted({item["source_id"] for item in all_evidence})
        source_urls = sorted({item["url"] for item in all_evidence})
        strategy = self._reference_digest(payload.get("strategy_reference"), "strategy_reference", required_hash="revision_hash")
        evaluation = self._reference_digest(payload.get("evaluation_reference"), "evaluation_reference", required_hash="result_digest")
        content_payload = {
            "schema": "notch.creator-research-note/1",
            "title": title,
            "thesis": thesis,
            "reference": reference,
            "position": position,
            "supporting_evidence": supporting,
            "contradictory_evidence": contradictory,
            "observation_cutoff": cutoff,
            "strategy_reference": strategy,
            "evaluation_reference": evaluation,
        }
        return CreatorResearchNote(
            note_id=note_id,
            creator_account=creator_account,
            creator_verified=True,
            status=status,
            revision=revision,
            title=title,
            thesis=thesis,
            reference=reference,
            position=position,
            supporting_evidence=supporting,
            contradictory_evidence=contradictory,
            observation_cutoff=cutoff,
            source_ids=source_ids,
            source_urls=source_urls,
            strategy_reference=strategy,
            evaluation_reference=evaluation,
            content_digest=_digest(content_payload),
            evidence_digest=_digest({"observation_cutoff": cutoff, "evidence": all_evidence}),
            created_at=created_at,
            updated_at=updated_at,
            published_at=(existing.published_at if existing and status == "PUBLISHED" else None),
            withdrawn_at=None,
            withdrawal_reason=None,
        )

    def _reference(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise CreatorNotesError("INVALID_REFERENCE", "reference must be an object")
        kind = _clean_text(value.get("kind"), "reference.kind", max_length=20).lower()
        if kind not in _REFERENCE_KINDS:
            raise CreatorNotesError("INVALID_REFERENCE", "reference.kind must be market or topic")
        reference_id = _clean_text(value.get("id"), "reference.id", max_length=200)
        label = _clean_text(value.get("label", reference_id), "reference.label", max_length=240)
        if kind == "market":
            if self.chain.get_market(reference_id) is None:
                raise CreatorNotesError("REFERENCE_NOT_FOUND", "referenced market is not available", status=404)
        else:
            if self.radar.get_candidate(reference_id) is None:
                raise CreatorNotesError("REFERENCE_NOT_FOUND", "referenced research topic is not available", status=404)
        return {"kind": kind, "id": reference_id, "label": label}

    def _evidence(
        self,
        value: Any,
        field: str,
        cutoff: str,
        reference: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise CreatorNotesError("INVALID_EVIDENCE", f"{field} must be an array")
        result: list[dict[str, Any]] = []
        cutoff_dt = _safe_parse_iso(cutoff)
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise CreatorNotesError("INVALID_EVIDENCE", f"{field}[{index}] must be an object")
            source_id = _source_id(item.get("source_id"), f"{field}[{index}].source_id")
            if not self._source_is_backed(source_id, reference):
                raise CreatorNotesError(
                    "SOURCE_NOT_BACKED",
                    f"{field}[{index}].source_id is not present in the referenced Wikimedia observation",
                    details={"field": field, "index": index, "source_id": source_id},
                )
            url = _https_url(item.get("url"), f"{field}[{index}].url")
            claim = _clean_text(item.get("claim"), f"{field}[{index}].claim", max_length=800)
            observed_at = _clean_text(item.get("observed_at"), f"{field}[{index}].observed_at", max_length=80)
            observed_dt = _safe_parse_iso(observed_at)
            if observed_dt is None:
                raise CreatorNotesError("INVALID_EVIDENCE_DATE", f"{field}[{index}].observed_at must be ISO-8601")
            if cutoff_dt is not None and observed_dt > cutoff_dt:
                raise CreatorNotesError(
                    "LOOKAHEAD_BLOCKED",
                    f"{field}[{index}] was observed after the note cutoff",
                    details={"field": field, "index": index},
                )
            result.append(
                {
                    "source_id": source_id,
                    "url": url,
                    "observed_at": iso_utc(observed_dt),
                    "claim": claim,
                }
            )
        return result

    def _source_is_backed(self, source_id: str, reference: dict[str, Any]) -> bool:
        if reference["kind"] == "market":
            market = self.chain.get_market(reference["id"]) or {}
            return isinstance(market, dict) and source_id == market.get("source_id") == "wikimedia-pageviews-v1"

        candidate = self.radar.get_candidate(reference["id"]) or {}
        if not isinstance(candidate, dict):
            return False
        if source_id == "wikimedia-pageviews-v1":
            signals = candidate.get("discovery_signals") or {}
            coverage = candidate.get("settlement_coverage") or {}
            return (
                "wikimedia" in {str(item).lower() for item in (signals.get("sources") or [])}
                or coverage.get("source") == "wikimedia-pageviews-v1"
            )

        evidence = list(candidate.get("discovery_evidence") or []) + list(candidate.get("source_identities") or [])
        if any(str(item.get("source_id")) == source_id for item in evidence if isinstance(item, dict)):
            return True

        parts = source_id.split(":", 3)
        if len(parts) != 4 or parts[0] != "wikimedia" or parts[1] != "en.wikipedia.org":
            return False
        coverage = candidate.get("settlement_coverage") or {}
        article = (
            coverage.get("article")
            or (candidate.get("discovery_signals") or {}).get("settlement_article")
            or candidate.get("title")
        )
        if not article or normalize_name(parts[2]) != normalize_name(str(article)):
            return False
        return any(
            isinstance(row, dict) and str(row.get("date")) == parts[3]
            for row in (coverage.get("daily_views") or [])
        )

    def _reference_digest(self, value: Any, field: str, *, required_hash: str) -> dict[str, Any] | None:
        if value in (None, ""):
            return None
        if not isinstance(value, dict):
            raise CreatorNotesError("INVALID_REFERENCE", f"{field} must be an object")
        identifier = _clean_text(value.get("id"), f"{field}.id", max_length=200)
        digest = _clean_text(value.get(required_hash), f"{field}.{required_hash}", max_length=160)
        if not _DIGEST_RE.fullmatch(digest):
            raise CreatorNotesError("INVALID_DIGEST", f"{field}.{required_hash} must be a stable digest")
        # Explicitly retain the supplied revision/result identity. This service
        # does not pretend to verify browser-local strategy artifacts.
        return {
            "id": identifier,
            required_hash: digest,
            "integrity": "as_supplied",
        }

    def _with_history(self, note: CreatorResearchNote, *, private: bool) -> dict[str, Any]:
        result = note.to_dict() if private else note.public_dict()
        result["revision_history"] = [
            {
                "revision": item.get("revision"),
                "status": item.get("status"),
                "content_digest": item.get("content_digest"),
                "evidence_digest": item.get("evidence_digest"),
                "created_at": item.get("updated_at") or item.get("created_at"),
            }
            for item in self.store.revisions(note.note_id)
        ]
        return result

    def _now_iso(self) -> str:
        return iso_utc(self.clock().astimezone(timezone.utc)) or ""
