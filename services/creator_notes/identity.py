"""NEP-413 wallet ownership challenges for Creator Studio.

The API never receives a private key and never signs or broadcasts a transaction.
A wallet signs a short-lived, domain-bound challenge; the server verifies the
NEP-413 Ed25519 signature and confirms that the public key is an on-chain access
key for the claimed account before issuing an opaque, expiring session token.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import struct
from datetime import datetime, timedelta, timezone
from typing import Any

from services.intents.balance import NearRpcClient, NearRpcError
from services.intents.signature import verify_ed25519_signature_bytes
from services.intents.validation import is_near_account
from services.trend_radar.models import iso_utc, now_utc

from .store import CreatorNotesStore


class CreatorIdentityError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


NEP413_TAG = 2_147_484_061
CHALLENGE_RECIPIENT = "notch.creator"
CHALLENGE_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=1)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return iso_utc(_utc(value)) or ""


def _borsh_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def nep413_payload(
    *,
    message: str,
    nonce: bytes,
    recipient: str,
    callback_url: str | None = None,
) -> bytes:
    """Serialize the exact NEP-413 payload used by wallet-selector."""
    if len(nonce) != 32:
        raise ValueError("NEP-413 nonce must be exactly 32 bytes")
    payload = struct.pack("<I", NEP413_TAG)
    payload += _borsh_string(message)
    payload += nonce
    payload += _borsh_string(recipient)
    if callback_url:
        payload += b"\x01" + _borsh_string(callback_url)
    else:
        payload += b"\x00"
    return payload


def verify_nep413_signature(
    *,
    public_key: str,
    signature_b64: str,
    message: str,
    nonce_b64: str,
    recipient: str,
    callback_url: str | None = None,
) -> bool:
    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
        signature = base64.b64decode(signature_b64, validate=True)
        payload_hash = hashlib.sha256(
            nep413_payload(
                message=message,
                nonce=nonce,
                recipient=recipient,
                callback_url=callback_url,
            )
        ).digest()
    except (ValueError, TypeError):
        return False
    return verify_ed25519_signature_bytes(public_key, signature, payload_hash)


class CreatorIdentityService:
    def __init__(
        self,
        *,
        store: CreatorNotesStore,
        reader: NearRpcClient,
        challenge_recipient: str = CHALLENGE_RECIPIENT,
        challenge_ttl: timedelta = CHALLENGE_TTL,
        session_ttl: timedelta = SESSION_TTL,
        network: str = "testnet",
        clock=now_utc,
    ) -> None:
        self.store = store
        self.reader = reader
        self.challenge_recipient = challenge_recipient
        self.challenge_ttl = challenge_ttl
        self.session_ttl = session_ttl
        self.network = network
        self.clock = clock

    def create_challenge(self, account_id: str) -> dict[str, Any]:
        account_id = str(account_id or "").strip()
        if not is_near_account(account_id):
            raise CreatorIdentityError("INVALID_ACCOUNT", "account_id is not a valid NEAR account")
        now = _utc(self.clock())
        expires = now + self.challenge_ttl
        nonce_b64 = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        if self.network != "testnet":
            raise CreatorIdentityError("TESTNET_IDENTITY_REQUIRED", "Creator Studio identity is restricted to NEAR Testnet", status=503)
        message = (
            "Notch Creator Studio ownership challenge\n"
            "Network: NEAR Testnet\n"
            f"Account: {account_id}\n"
            f"Nonce: {nonce_b64}\n"
            f"Expires: {_iso(expires)}"
        )
        return self.store.create_challenge(
            account_id=account_id,
            nonce_b64=nonce_b64,
            message=message,
            recipient=self.challenge_recipient,
            created_at=_iso(now),
            expires_at=_iso(expires),
            network=self.network,
        )

    def verify(
        self,
        *,
        challenge_id: str,
        account_id: str,
        public_key: str,
        signature: str,
    ) -> dict[str, Any]:
        challenge = self.store.get_challenge(challenge_id)
        if challenge is None:
            raise CreatorIdentityError("CHALLENGE_NOT_FOUND", "ownership challenge was not found", status=404)
        if challenge["account_id"] != account_id:
            raise CreatorIdentityError("CHALLENGE_ACCOUNT_MISMATCH", "challenge account does not match")
        if challenge.get("network", "testnet") != self.network:
            raise CreatorIdentityError("CHALLENGE_NETWORK_MISMATCH", "ownership challenge is bound to a different NEAR network")
        now = _utc(self.clock())
        now_iso = _iso(now)
        if challenge["used_at"] is not None:
            raise CreatorIdentityError("CHALLENGE_USED", "ownership challenge has already been used", status=409)
        if challenge["expires_at"] <= now_iso:
            raise CreatorIdentityError("CHALLENGE_EXPIRED", "ownership challenge has expired", status=400)
        if not public_key.startswith("ed25519:"):
            raise CreatorIdentityError("UNSUPPORTED_PUBLIC_KEY", "only ed25519 wallet keys are supported")
        if not signature:
            raise CreatorIdentityError("MISSING_SIGNATURE", "wallet signature is required")

        try:
            access_key = self._view_access_key(account_id, public_key)
        except NearRpcError as exc:
            raise CreatorIdentityError(
                "IDENTITY_LOOKUP_UNAVAILABLE",
                "could not verify the wallet key against NEAR Testnet",
                status=503,
            ) from exc
        if not access_key:
            raise CreatorIdentityError(
                "PUBLIC_KEY_NOT_AUTHORIZED",
                "the signed public key is not an access key for this account",
                status=403,
            )
        if not verify_nep413_signature(
            public_key=public_key,
            signature_b64=signature,
            message=challenge["message"],
            nonce_b64=challenge["nonce_b64"],
            recipient=challenge["recipient"],
        ):
            raise CreatorIdentityError("INVALID_SIGNATURE", "wallet signature could not be verified", status=403)
        if not self.store.consume_challenge(challenge_id, now_iso):
            raise CreatorIdentityError("CHALLENGE_USED", "ownership challenge has already been used", status=409)
        expires = now + self.session_ttl
        token = self.store.create_session(
            account_id=account_id,
            public_key=public_key,
            created_at=now_iso,
            expires_at=_iso(expires),
            network=self.network,
        )
        return {
            "account_id": account_id,
            "public_key": public_key,
            "verified": True,
            "network": self.network,
            "verification_method": "NEP-413 + final NEAR access-key lookup",
            "session_token": token,
            "session_expires_at": _iso(expires),
        }

    def session(self, token: str | None) -> dict[str, Any]:
        if not token:
            raise CreatorIdentityError("AUTH_REQUIRED", "a verified Creator Studio session is required", status=401)
        row = self.store.get_session(token, _iso(_utc(self.clock())))
        if not row or row.get("network", "testnet") != self.network:
            raise CreatorIdentityError("AUTH_INVALID", "Creator Studio session is missing, expired, revoked, or network-bound elsewhere", status=401)
        return row

    def revoke(self, token: str | None) -> dict[str, Any]:
        row = self.session(token)
        if not token or not self.store.revoke_session(token, _iso(_utc(self.clock()))):
            raise CreatorIdentityError("AUTH_INVALID", "Creator Studio session is missing or already revoked", status=401)
        return {"revoked": True, "account_id": row["account_id"], "revoked_at": _iso(_utc(self.clock()))}

    def access_key_is_authorized(self, account_id: str, public_key: str) -> bool:
        return self._view_access_key(account_id, public_key) is not None

    def _view_access_key(self, account_id: str, public_key: str) -> dict[str, Any] | None:
        if hasattr(self.reader, "view_access_key"):
            result = self.reader.view_access_key(account_id, public_key)
        else:
            result = self.reader._rpc(
                "query",
                {
                    "request_type": "view_access_key",
                    "finality": "final",
                    "account_id": account_id,
                    "public_key": public_key,
                },
            )
        if not isinstance(result, dict):
            return None
        return result.get("access_key") if "access_key" in result else result
