"""Validation and lifecycle rules for verifiable creator research notes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlparse

from services.intents.balance import NearRpcClient, NearRpcError
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
_PREMIUM_BODY_MAX = 50_000
_PAYMENT_INTENT_TTL = timedelta(minutes=15)
_PAYMENT_GAS_TGAS = 30
_PAYMENT_STATUSES = {"PENDING", "VERIFIED", "FAILED", "EXPIRED"}


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_parse_iso(value: str | None) -> datetime | None:
    try:
        return parse_iso(value)
    except (TypeError, ValueError):
        return None


def _parse_required(value: str) -> datetime:
    parsed = _safe_parse_iso(value)
    if parsed is None:
        raise CreatorNotesError("INVALID_TIMESTAMP", "stored payment timestamp is invalid", status=500)
    return parsed


def _rpc_success(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in value for key in ("SuccessValue", "SuccessReceiptId"))
    return isinstance(value, str) and value.startswith("Success")


def _rpc_failure(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in value for key in ("Failure", "FailureValue"))
    return isinstance(value, str) and value.startswith("Failure")


def _function_call(action: Any) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    call = action.get("FunctionCall") or action.get("function_call")
    return call if isinstance(call, dict) else None


def _decode_json_args(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _transfer_event_matches(log: Any, intent: dict[str, Any]) -> bool:
    if not isinstance(log, str) or not log.startswith("EVENT_JSON:"):
        return False
    try:
        event = json.loads(log[len("EVENT_JSON:"):])
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(event, dict) or str(event.get("standard", "")).lower() != "nep141" or event.get("event") != "ft_transfer":
        return False
    data = event.get("data") if isinstance(event.get("data"), list) else [event.get("data")]
    return any(
        isinstance(item, dict)
        and item.get("old_owner_id") == intent["buyer_account"]
        and item.get("new_owner_id") == intent["recipient_account"]
        and str(item.get("amount")) == intent["amount_base_units"]
        for item in data
    )


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
        payment_token: str | None = None,
        payment_network: str = "testnet",
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.store = store
        self.reader = reader
        self.chain = chain
        self.radar = radar
        self.clock = clock
        chain_config = getattr(chain, "config", None)
        configured_token = (
            chain_config.get("collateral_token")
            if isinstance(chain_config, dict)
            else getattr(chain_config, "collateral_token", None)
        )
        self.payment_token = payment_token or configured_token
        self.payment_network = payment_network
        self.identity = identity or CreatorIdentityService(store=store, reader=reader, network=payment_network, clock=clock)
        self._payment_lock = threading.RLock()

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

    def revoke_identity(self, token: str | None) -> dict[str, Any]:
        try:
            return self.identity.revoke(token)
        except CreatorIdentityError as exc:
            raise CreatorNotesError(exc.code, str(exc), status=exc.status) from exc

    def _session(self, token: str | None) -> dict[str, Any]:
        try:
            return self.identity.session(token)
        except CreatorIdentityError as exc:
            raise CreatorNotesError(exc.code, str(exc), status=exc.status) from exc

    # ------------------------------------------------------------------
    # Verified payout destination and payment configuration
    # ------------------------------------------------------------------
    def payout_status(self, token: str | None) -> dict[str, Any]:
        session = self._session(token)
        record = self.store.get_payout_account(session["account_id"])
        return {
            "configured": record is not None,
            "creator_account": session["account_id"],
            "network": self.payment_network,
            "token_contract": self.payment_token,
            "payout_account": record["payout_account"] if record else None,
            "token_symbol": record["token_symbol"] if record else None,
            "token_decimals": record["token_decimals"] if record else None,
            "storage_registered": record["storage_registered"] if record else False,
            "verified_at": record["verified_at"] if record else None,
        }

    def configure_payout(self, token: str | None, requested_account: str | None = None) -> dict[str, Any]:
        session = self._session(token)
        payout_account = session["account_id"]
        if requested_account and requested_account != payout_account:
            raise CreatorNotesError(
                "PAYOUT_ACCOUNT_MUST_MATCH_SESSION",
                "V1 payout configuration must use the currently verified creator account",
                status=403,
            )
        try:
            authorized = self.identity.access_key_is_authorized(
                payout_account, session["public_key"]
            )
        except NearRpcError as exc:
            raise CreatorNotesError(
                "PAYOUT_KEY_LOOKUP_UNAVAILABLE",
                "could not recheck the payout account access key on NEAR Testnet",
                status=503,
            ) from exc
        if not authorized:
            raise CreatorNotesError(
                "PAYOUT_ACCOUNT_NOT_AUTHORIZED",
                "the verified payout account key is no longer authorized",
                status=403,
            )
        metadata = self._payment_token_metadata()
        try:
            storage = self.chain.storage_balance(metadata["contract"], payout_account)
        except Exception as exc:
            raise CreatorNotesError(
                "PAYOUT_STORAGE_LOOKUP_UNAVAILABLE",
                "could not verify NEP-141 storage registration for the payout account",
                status=503,
            ) from exc
        if not isinstance(storage, dict) or "total" not in storage:
            raise CreatorNotesError(
                "PAYOUT_STORAGE_NOT_REGISTERED",
                "the payout account is not registered with the configured Testnet token",
                status=400,
                details={"token_contract": metadata["contract"]},
            )
        now = self._now_iso()
        saved = self.store.save_payout_account(
            {
                "creator_account": session["account_id"],
                "payout_account": payout_account,
                "public_key": session["public_key"],
                "token_contract": metadata["contract"],
                "token_symbol": metadata["symbol"],
                "token_decimals": metadata["decimals"],
                "storage_registered": True,
                "verified_at": now,
                "updated_at": now,
            }
        )
        return {
            "configured": True,
            "creator_account": session["account_id"],
            "network": self.payment_network,
            "token_contract": saved["token_contract"],
            "payout_account": saved["payout_account"],
            "token_symbol": saved["token_symbol"],
            "token_decimals": saved["token_decimals"],
            "storage_registered": bool(saved["storage_registered"]),
            "verified_at": saved["verified_at"],
        }

    def _payment_token_metadata(self) -> dict[str, Any]:
        token = str(self.payment_token or "").strip()
        if self.payment_network != "testnet" or ".testnet" not in token.lower():
            raise CreatorNotesError(
                "TESTNET_PAYMENT_REQUIRED",
                "Creator Studio payments are restricted to a configured NEAR Testnet token",
                status=503,
            )
        if not hasattr(self.chain, "ft_metadata"):
            raise CreatorNotesError(
                "PAYMENT_TOKEN_UNAVAILABLE",
                "the configured payment token metadata reader is unavailable",
                status=503,
            )
        try:
            metadata = self.chain.ft_metadata(token)
        except Exception as exc:
            raise CreatorNotesError(
                "PAYMENT_TOKEN_UNAVAILABLE",
                "could not read the configured Testnet token metadata",
                status=503,
            ) from exc
        if not isinstance(metadata, dict):
            raise CreatorNotesError("PAYMENT_TOKEN_INVALID", "the configured token metadata is invalid", status=503)
        symbol = metadata.get("symbol")
        decimals = metadata.get("decimals")
        if not isinstance(symbol, str) or not symbol.strip() or isinstance(decimals, bool):
            raise CreatorNotesError("PAYMENT_TOKEN_INVALID", "the configured token metadata is incomplete", status=503)
        try:
            decimals = int(decimals)
        except (TypeError, ValueError) as exc:
            raise CreatorNotesError("PAYMENT_TOKEN_INVALID", "the configured token decimals are invalid", status=503) from exc
        if decimals < 0 or decimals > 24:
            raise CreatorNotesError("PAYMENT_TOKEN_INVALID", "the configured token decimals are out of range", status=503)
        spec = metadata.get("spec")
        if spec is not None and not str(spec).startswith("ft-"):
            raise CreatorNotesError("PAYMENT_TOKEN_INVALID", "the configured token is not NEP-141 compatible", status=503)
        return {"contract": token, "symbol": symbol.strip(), "decimals": decimals}

    def _ensure_payout_usable(self, payout: dict[str, Any] | None, metadata: dict[str, Any]) -> None:
        if not payout or not payout.get("storage_registered"):
            raise CreatorNotesError("PAYOUT_UNAVAILABLE", "the creator has not configured a verified Testnet payout account", status=409)
        if payout.get("token_contract") != metadata["contract"]:
            raise CreatorNotesError("PAYOUT_TOKEN_MISMATCH", "the creator payout token is not the configured Testnet token", status=409)
        try:
            authorized = self.identity.access_key_is_authorized(payout["payout_account"], payout["public_key"])
            storage = self.chain.storage_balance(metadata["contract"], payout["payout_account"])
        except NearRpcError as exc:
            raise CreatorNotesError("PAYOUT_KEY_LOOKUP_UNAVAILABLE", "could not recheck the creator payout account on NEAR Testnet", status=503) from exc
        except Exception as exc:
            raise CreatorNotesError("PAYOUT_STORAGE_LOOKUP_UNAVAILABLE", "could not recheck NEP-141 storage registration for the payout account", status=503) from exc
        if not authorized:
            raise CreatorNotesError("PAYOUT_ACCOUNT_NOT_AUTHORIZED", "the creator payout account key is no longer authorized", status=409)
        if not isinstance(storage, dict) or "total" not in storage:
            raise CreatorNotesError("PAYOUT_STORAGE_NOT_REGISTERED", "the creator payout account is no longer registered with the configured token", status=409)

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

    # ------------------------------------------------------------------
    # Paid research intents, receipt verification and protected content.
    # ------------------------------------------------------------------
    def _ensure_buyer_funded(self, account_id: str, token_contract: str, amount_base_units: int) -> None:
        try:
            token_balance = int(self.chain.ft_balance(token_contract, account_id))
            native_balance = int(self.chain.native_balance(account_id))
        except NearRpcError as exc:
            raise CreatorNotesError("BUYER_BALANCE_UNAVAILABLE", "could not verify the buyer's Testnet token and NEAR balances", status=503) from exc
        except (TypeError, ValueError, AttributeError) as exc:
            raise CreatorNotesError("BUYER_BALANCE_UNAVAILABLE", "could not verify the buyer's Testnet token and NEAR balances", status=503) from exc
        except Exception as exc:
            raise CreatorNotesError("BUYER_BALANCE_UNAVAILABLE", "could not verify the buyer's Testnet token and NEAR balances", status=503) from exc
        if token_balance < amount_base_units:
            raise CreatorNotesError("INSUFFICIENT_TOKEN_BALANCE", "the buyer wallet does not have enough of the configured Testnet token", status=409)
        if native_balance <= 0:
            raise CreatorNotesError("INSUFFICIENT_GAS_BALANCE", "the buyer wallet needs a positive NEAR Testnet balance for gas", status=409)

    def create_payment_intent(self, token: str | None, note_id: str) -> dict[str, Any]:
        session = self._session(token)
        note = self.store.get_note(note_id)
        if note is None or note.status != "PUBLISHED":
            raise CreatorNotesError("NOTE_NOT_FOUND", "published research note was not found", status=404)
        if not note.premium_enabled:
            raise CreatorNotesError("PREMIUM_NOT_ENABLED", "this research note does not offer a premium unlock", status=409)
        if session["account_id"] == note.creator_account:
            raise CreatorNotesError("CREATOR_ACCESS", "the verified creator already has access to this revision", status=409)
        payout = self.store.get_payout_account(note.creator_account)
        metadata = self._payment_token_metadata()
        self._ensure_payout_usable(payout, metadata)
        if note.premium_token_contract != metadata["contract"] or note.premium_token_decimals != metadata["decimals"]:
            raise CreatorNotesError("PAYMENT_TOKEN_MISMATCH", "this pricing revision does not match the configured Testnet token", status=409)
        existing = self.store.get_entitlement_for_note(session["account_id"], note_id, note.revision)
        if existing:
            return {
                "status": "VERIFIED",
                "already_entitled": True,
                "note_id": note_id,
                "note_revision": note.revision,
                "entitlement": self._entitlement_view(existing),
            }
        amount = str(note.premium_price_base_units or "")
        if not re.fullmatch(r"[0-9]+", amount) or int(amount) <= 0:
            raise CreatorNotesError("INVALID_PREMIUM_PRICE", "the note has no valid stored base-unit price", status=409)
        self._ensure_buyer_funded(session["account_id"], metadata["contract"], int(amount))
        now = self._utc_now()
        intent_id = f"intent_{uuid.uuid4().hex}"
        record = {
            "intent_id": intent_id,
            "buyer_account": session["account_id"],
            "creator_account": note.creator_account,
            "note_id": note.note_id,
            "note_revision": note.revision,
            "content_digest": note.content_digest,
            "token_contract": metadata["contract"],
            "token_symbol": metadata["symbol"],
            "token_decimals": metadata["decimals"],
            "amount_base_units": amount,
            "recipient_account": payout["payout_account"],
            "memo": f"notch:research:{intent_id}",
            "status": "PENDING",
            "created_at": iso_utc(now) or "",
            "expires_at": iso_utc(now + _PAYMENT_INTENT_TTL) or "",
            "updated_at": iso_utc(now) or "",
        }
        try:
            intent = self.store.create_payment_intent(record)
        except CreatorNotesStoreError as exc:
            raise CreatorNotesError("PAYMENT_INTENT_CONFLICT", str(exc), status=409) from exc
        return self._intent_view(intent, note_title=note.title)

    def payment_status(self, token: str | None, intent_id: str) -> dict[str, Any]:
        session = self._session(token)
        intent = self.store.get_payment_intent(intent_id)
        if intent is None:
            raise CreatorNotesError("PAYMENT_INTENT_NOT_FOUND", "payment intent was not found", status=404)
        if session["account_id"] not in {intent["buyer_account"], intent["creator_account"]}:
            raise CreatorNotesError("PAYMENT_INTENT_FORBIDDEN", "only the buyer or creator can inspect this payment intent", status=403)
        if intent["status"] == "PENDING" and self._utc_now() >= _parse_required(intent["expires_at"]):
            intent = self.store.update_payment_intent(
                intent_id, status="EXPIRED", updated_at=self._now_iso(), failure_code="INTENT_EXPIRED", failure_message="payment intent expired"
            ) or intent
        return self._intent_view(intent)

    def purchases(self, token: str | None, limit: int = 50) -> dict[str, Any]:
        session = self._session(token)
        return {
            "buyer_entitlements": [self._entitlement_view(item) for item in self.store.list_entitlements(buyer_account=session["account_id"], limit=limit)],
            "creator_sales": [self._entitlement_view(item) for item in self.store.list_entitlements(creator_account=session["account_id"], limit=limit)],
        }

    def premium_content(self, token: str | None, note_id: str, revision: int | None = None) -> dict[str, Any]:
        session = self._session(token)
        current = self.store.get_note(note_id)
        if current is None:
            raise CreatorNotesError("NOTE_NOT_FOUND", "research note was not found", status=404)
        entitlement: dict[str, Any] | None = None
        if session["account_id"] == current.creator_account:
            target = self.store.get_revision(note_id, revision) if revision is not None else current
        else:
            entitlement = self.store.get_entitlement_for_note(session["account_id"], note_id, revision)
            if entitlement is None:
                raise CreatorNotesError("PREMIUM_ACCESS_REQUIRED", "a verified purchase entitlement is required", status=403)
            target = self.store.get_revision(note_id, int(entitlement["note_revision"]))
        if target is None or not target.premium_enabled or target.premium_body is None:
            raise CreatorNotesError("PREMIUM_NOT_AVAILABLE", "the requested premium revision is not available", status=404)
        return {
            "note_id": target.note_id,
            "revision": target.revision,
            "content_digest": target.content_digest,
            "premium": {
                "body": target.premium_body,
                "body_digest": target.premium_body_digest,
                "price_base_units": target.premium_price_base_units,
                "token_contract": target.premium_token_contract,
                "token_symbol": target.premium_token_symbol,
                "token_decimals": target.premium_token_decimals,
            },
            "entitlement": self._entitlement_view(entitlement) if entitlement else None,
            "access": "creator" if entitlement is None else "purchased_revision",
        }

    def verify_payment(self, token: str | None, intent_id: str, tx_hash: str) -> dict[str, Any]:
        session = self._session(token)
        tx_hash = _clean_text(tx_hash, "tx_hash", max_length=128)
        with self._payment_lock:
            intent = self.store.get_payment_intent(intent_id)
            if intent is None:
                raise CreatorNotesError("PAYMENT_INTENT_NOT_FOUND", "payment intent was not found", status=404)
            if session["account_id"] != intent["buyer_account"]:
                raise CreatorNotesError("PAYMENT_VERIFICATION_FORBIDDEN", "only the authenticated buyer can submit payment evidence", status=403)
            if intent["status"] == "VERIFIED":
                if intent.get("tx_hash") != tx_hash:
                    raise CreatorNotesError("PAYMENT_ALREADY_VERIFIED", "this payment intent is already verified with a different transaction", status=409)
                return self._intent_view(intent)
            if intent["status"] in {"FAILED", "EXPIRED"}:
                raise CreatorNotesError("PAYMENT_INTENT_CLOSED", "this payment intent is no longer verifiable", status=409)
            if self._utc_now() >= _parse_required(intent["expires_at"]):
                intent = self.store.update_payment_intent(
                    intent_id, status="EXPIRED", updated_at=self._now_iso(), failure_code="INTENT_EXPIRED", failure_message="payment intent expired"
                ) or intent
                raise CreatorNotesError("PAYMENT_INTENT_EXPIRED", "the payment intent expired before final verification", status=409)
            reused = self.store.find_payment_intent_by_tx(tx_hash)
            if reused and reused["intent_id"] != intent_id:
                self.store.update_payment_intent(
                    intent_id, status="FAILED", updated_at=self._now_iso(), failure_code="TX_ALREADY_USED", failure_message="transaction evidence is already attached to another payment intent"
                )
                return self._intent_view(self.store.get_payment_intent(intent_id) or intent)
            try:
                result = self._inspect_payment_transaction(intent, tx_hash)
            except NearRpcError as exc:
                raise CreatorNotesError(
                    "PAYMENT_VERIFICATION_UNAVAILABLE",
                    "finalized NEAR Testnet receipt verification is temporarily unavailable",
                    status=503,
                ) from exc
            if result["status"] == "PENDING":
                updated = self.store.update_payment_intent(
                    intent_id, updated_at=self._now_iso(), failure_code=result.get("failure_code"), failure_message=result.get("failure_message")
                ) or intent
                return self._intent_view(updated)
            if result["status"] == "FAILED":
                updated = self.store.update_payment_intent(
                    intent_id,
                    status="FAILED",
                    updated_at=self._now_iso(),
                    tx_hash=tx_hash,
                    receipt_id=result.get("receipt_id"),
                    failure_code=result.get("failure_code"),
                    failure_message=result.get("failure_message"),
                ) or intent
                return self._intent_view(updated)
            entitlement = self.store.create_entitlement(
                {
                    "entitlement_id": f"entitlement_{uuid.uuid4().hex}",
                    "intent_id": intent_id,
                    "buyer_account": intent["buyer_account"],
                    "creator_account": intent["creator_account"],
                    "note_id": intent["note_id"],
                    "note_revision": int(intent["note_revision"]),
                    "content_digest": intent["content_digest"],
                    "tx_hash": tx_hash,
                    "receipt_id": result["receipt_id"],
                    "granted_at": self._now_iso(),
                }
            )
            if entitlement["intent_id"] != intent_id:
                updated = self.store.update_payment_intent(
                    intent_id,
                    status="FAILED",
                    updated_at=self._now_iso(),
                    tx_hash=tx_hash,
                    receipt_id=result["receipt_id"],
                    failure_code="ALREADY_ENTITLED",
                    failure_message="a buyer entitlement for this immutable revision already exists",
                ) or intent
                return self._intent_view(updated)
            updated = self.store.update_payment_intent(
                intent_id,
                status="VERIFIED",
                updated_at=self._now_iso(),
                tx_hash=tx_hash,
                receipt_id=result["receipt_id"],
                failure_code=None,
                failure_message=None,
            ) or intent
            return self._intent_view(updated, entitlement=entitlement)

    def _inspect_payment_transaction(self, intent: dict[str, Any], tx_hash: str) -> dict[str, Any]:
        status = self._transaction_status(tx_hash, intent["buyer_account"])
        if not isinstance(status, dict):
            return {"status": "PENDING", "failure_code": "FINALITY_PENDING", "failure_message": "transaction status is not available yet"}
        tx_status = status.get("status")
        if not _rpc_success(tx_status):
            if _rpc_failure(tx_status):
                return {"status": "FAILED", "failure_code": "TRANSACTION_FAILED", "failure_message": "the finalized transaction failed"}
            return {"status": "PENDING", "failure_code": "FINALITY_PENDING", "failure_message": "the transaction is not finalized yet"}
        transaction = status.get("transaction")
        if not isinstance(transaction, dict):
            return {"status": "FAILED", "failure_code": "TRANSACTION_MALFORMED", "failure_message": "finalized status omitted the transaction"}
        if transaction.get("hash") != tx_hash or transaction.get("signer_id") != intent["buyer_account"]:
            return {"status": "FAILED", "failure_code": "BUYER_MISMATCH", "failure_message": "transaction signer does not match the authenticated buyer"}
        if transaction.get("receiver_id") != intent["token_contract"]:
            return {"status": "FAILED", "failure_code": "TOKEN_CONTRACT_MISMATCH", "failure_message": "transaction receiver is not the configured NEP-141 token"}
        transfer = None
        for action in transaction.get("actions") or []:
            call = _function_call(action)
            if call and call.get("method_name") == "ft_transfer":
                args = _decode_json_args(call.get("args"))
                if args:
                    transfer = args
                    break
        if not isinstance(transfer, dict):
            return {"status": "FAILED", "failure_code": "TRANSFER_ACTION_MISSING", "failure_message": "transaction did not contain an ft_transfer action"}
        if transfer.get("receiver_id") != intent["recipient_account"]:
            return {"status": "FAILED", "failure_code": "RECIPIENT_MISMATCH", "failure_message": "the transfer recipient does not match the verified creator payout account"}
        if str(transfer.get("amount")) != intent["amount_base_units"]:
            return {"status": "FAILED", "failure_code": "AMOUNT_MISMATCH", "failure_message": "the transferred base-unit amount does not match the invoice"}
        if transfer.get("memo") != intent["memo"]:
            return {"status": "FAILED", "failure_code": "MEMO_MISMATCH", "failure_message": "the transfer memo does not match the payment intent"}
        receipts = status.get("receipts_outcome")
        if not isinstance(receipts, list) or not receipts:
            return {"status": "PENDING", "failure_code": "RECEIPT_PENDING", "failure_message": "the finalized receipt evidence is not available yet"}
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            outcome = receipt.get("outcome")
            if not isinstance(outcome, dict):
                continue
            if not _rpc_success(outcome.get("status")):
                return {"status": "FAILED", "failure_code": "RECEIPT_FAILED", "failure_message": "the token receipt failed"}
            if outcome.get("executor_id") != intent["token_contract"]:
                continue
            receipt_id = receipt.get("id")
            block_hash = receipt.get("block_hash")
            if not isinstance(receipt_id, str) or not isinstance(block_hash, str):
                continue
            if not self._final_block_is_present(block_hash):
                return {"status": "PENDING", "failure_code": "RECEIPT_FINALITY_PENDING", "failure_message": "the token receipt block is not finalized yet", "receipt_id": receipt_id}
            if any(_transfer_event_matches(log, intent) for log in (outcome.get("logs") or [])):
                return {"status": "VERIFIED", "receipt_id": receipt_id}
        return {"status": "FAILED", "failure_code": "TRANSFER_EVENT_MISSING", "failure_message": "a successful NEP-141 transfer event was not found in the finalized receipt"}

    def _transaction_status(self, tx_hash: str, signer_id: str) -> Any:
        if hasattr(self.reader, "transaction_status"):
            return self.reader.transaction_status(tx_hash, signer_id)
        return self.reader._rpc("EXPERIMENTAL_tx_status", [tx_hash, signer_id])

    def _final_block_is_present(self, block_hash: str) -> bool:
        if hasattr(self.reader, "block_by_id"):
            block = self.reader.block_by_id(block_hash)
        else:
            block = self.reader._rpc("block", {"block_id": block_hash})
        header = block.get("header") if isinstance(block, dict) else None
        if not isinstance(header, dict):
            return False
        try:
            height = int(header.get("height", -1))
        except (TypeError, ValueError):
            return False
        return header.get("hash") == block_hash and height >= 0

    def _intent_view(
        self,
        intent: dict[str, Any],
        *,
        note_title: str | None = None,
        entitlement: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if note_title is None:
            note = self.store.get_note(str(intent["note_id"]))
            note_title = note.title if note else "Research note"
        value = {
            "intent_id": intent["intent_id"],
            "status": intent["status"],
            "buyer_account": intent["buyer_account"],
            "creator_account": intent["creator_account"],
            "note_id": intent["note_id"],
            "note_title": note_title,
            "note_revision": int(intent["note_revision"]),
            "content_digest": intent["content_digest"],
            "network": self.payment_network,
            "token_contract": intent["token_contract"],
            "token_symbol": intent["token_symbol"],
            "token_decimals": int(intent["token_decimals"]),
            "amount_base_units": intent["amount_base_units"],
            "recipient_account": intent["recipient_account"],
            "memo": intent["memo"],
            "created_at": intent["created_at"],
            "expires_at": intent["expires_at"],
            "updated_at": intent["updated_at"],
            "tx_hash": intent.get("tx_hash"),
            "receipt_id": intent.get("receipt_id"),
            "failure_code": intent.get("failure_code"),
            "failure_message": intent.get("failure_message"),
            "action": {
                "receiver_id": intent["token_contract"],
                "method_name": "ft_transfer",
                "args": {
                    "receiver_id": intent["recipient_account"],
                    "amount": intent["amount_base_units"],
                    "memo": intent["memo"],
                },
                "gas_tgas": _PAYMENT_GAS_TGAS,
                "attached_deposit_yocto": "1",
            },
            "disclosure": {
                "testnet_only": True,
                "refund_policy": "No automatic refunds are provided by V1; verify the invoice before approving.",
                "user_approval_required": True,
                "notch_signs_or_broadcasts": False,
            },
        }
        if entitlement:
            value["entitlement"] = self._entitlement_view(entitlement)
        elif intent["status"] == "VERIFIED":
            existing = self.store.get_entitlement_for_note(intent["buyer_account"], intent["note_id"], int(intent["note_revision"]))
            if existing:
                value["entitlement"] = self._entitlement_view(existing)
        if intent.get("tx_hash"):
            value["explorer_url"] = f"https://testnet.nearblocks.io/txns/{intent['tx_hash']}"
        return value

    def _entitlement_view(self, record: dict[str, Any]) -> dict[str, Any]:
        intent = self.store.get_payment_intent(str(record["intent_id"])) or {}
        return {
            "entitlement_id": record["entitlement_id"],
            "intent_id": record["intent_id"],
            "buyer_account": record["buyer_account"],
            "creator_account": record["creator_account"],
            "note_id": record["note_id"],
            "note_revision": int(record["note_revision"]),
            "content_digest": record["content_digest"],
            "tx_hash": record["tx_hash"],
            "receipt_id": record["receipt_id"],
            "granted_at": record["granted_at"],
            "amount_base_units": intent.get("amount_base_units"),
            "token_contract": intent.get("token_contract"),
            "token_symbol": intent.get("token_symbol"),
            "recipient_account": intent.get("recipient_account"),
            "memo": intent.get("memo"),
            "explorer_url": f"https://testnet.nearblocks.io/txns/{record['tx_hash']}",
        }

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
        if note.premium_enabled:
            if not note.premium_body or not note.premium_price_base_units:
                raise CreatorNotesError("PREMIUM_INCOMPLETE", "premium publication requires a body and a positive price")
            payout = self.store.get_payout_account(note.creator_account)
            metadata = self._payment_token_metadata()
            try:
                self._ensure_payout_usable(payout, metadata)
            except CreatorNotesError as exc:
                if exc.code == "PAYOUT_UNAVAILABLE":
                    raise CreatorNotesError(
                        "PAYOUT_REQUIRED",
                        "configure a verified Testnet payout account before publishing a premium note",
                        status=409,
                    ) from exc
                raise
            if note.premium_token_contract != metadata["contract"]:
                raise CreatorNotesError(
                    "PAYOUT_TOKEN_MISMATCH",
                    "the verified payout token does not match this premium revision",
                    status=409,
                )

    def _decimal_to_base_units(self, value: Any, decimals: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CreatorNotesError("INVALID_PREMIUM_PRICE", "premium.price must be a decimal token amount")
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise CreatorNotesError("INVALID_PREMIUM_PRICE", "premium.price must be a decimal token amount") from exc
        if not amount.is_finite() or amount <= 0:
            raise CreatorNotesError("INVALID_PREMIUM_PRICE", "premium.price must be greater than zero")
        scaled = amount * (Decimal(10) ** decimals)
        if scaled != scaled.to_integral_value():
            raise CreatorNotesError(
                "INVALID_PREMIUM_PRICE_PRECISION",
                f"premium.price has more than {decimals} token decimals",
            )
        return str(int(scaled))

    def _premium_from_payload(
        self, payload: dict[str, Any], existing: CreatorResearchNote | None
    ) -> dict[str, Any]:
        raw = payload.get("premium")
        if raw is None:
            return {
                "enabled": False,
                "body": None,
                "body_digest": None,
                "price_base_units": None,
                "token_contract": None,
                "token_symbol": None,
                "token_decimals": None,
            }
        if not isinstance(raw, dict):
            raise CreatorNotesError("INVALID_PREMIUM", "premium must be an object")
        enabled = raw.get("enabled", bool(raw.get("body") or raw.get("price") or raw.get("price_base_units")))
        if not isinstance(enabled, bool):
            raise CreatorNotesError("INVALID_PREMIUM", "premium.enabled must be a boolean")
        if not enabled:
            return {
                "enabled": False,
                "body": None,
                "body_digest": None,
                "price_base_units": None,
                "token_contract": None,
                "token_symbol": None,
                "token_decimals": None,
            }
        body = _clean_text(raw.get("body"), "premium.body", max_length=_PREMIUM_BODY_MAX)
        metadata = self._payment_token_metadata()
        token_contract = str(raw.get("token_contract") or metadata["contract"])
        if token_contract != metadata["contract"]:
            raise CreatorNotesError(
                "PAYMENT_TOKEN_MISMATCH",
                "premium pricing must use the configured NEAR Testnet token",
            )
        if raw.get("price_base_units") is not None and raw.get("price") in (None, ""):
            base = _clean_text(raw.get("price_base_units"), "premium.price_base_units", max_length=80)
            if not re.fullmatch(r"[0-9]+", base) or int(base) <= 0:
                raise CreatorNotesError("INVALID_PREMIUM_PRICE", "premium.price_base_units must be a positive integer")
            if raw.get("token_decimals") is not None:
                try:
                    raw_decimals = int(raw["token_decimals"])
                except (TypeError, ValueError) as exc:
                    raise CreatorNotesError("INVALID_PREMIUM", "premium token decimals must be an integer") from exc
                if raw_decimals != metadata["decimals"]:
                    raise CreatorNotesError("PAYMENT_TOKEN_MISMATCH", "premium token decimals do not match the configured token")
        else:
            base = self._decimal_to_base_units(raw.get("price"), metadata["decimals"])
        return {
            "enabled": True,
            "body": body,
            "body_digest": _digest({"premium_body": body}),
            "price_base_units": base,
            "token_contract": metadata["contract"],
            "token_symbol": metadata["symbol"],
            "token_decimals": metadata["decimals"],
        }

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
        premium = self._premium_from_payload(payload, existing)
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
            "premium": premium,
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
            premium_enabled=premium["enabled"],
            premium_body=premium["body"],
            premium_body_digest=premium["body_digest"],
            premium_price_base_units=premium["price_base_units"],
            premium_token_contract=premium["token_contract"],
            premium_token_symbol=premium["token_symbol"],
            premium_token_decimals=premium["token_decimals"],
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

    def _utc_now(self) -> datetime:
        return self.clock().astimezone(timezone.utc)

    def _now_iso(self) -> str:
        return iso_utc(self._utc_now()) or ""
