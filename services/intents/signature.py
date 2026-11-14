"""Tidepool quote signature verification without external crypto dependencies.

Tidepool uses the 1Click quote signature scheme: stable JSON of the signed
request/quote fields plus timestamp, SHA-256, Base58, then Ed25519 signing.
This module verifies the published Tidepool maker key before a live quote can
be used for a deposit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import QuoteResponse

TIDEPOOL_MAKER_PUBLIC_KEY = "ed25519:U1Mu4u1nHnHmgABpCkfDGXt2FZj8k29UGqhkMAu4iWY"
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _Q - 2, _Q)) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)
_B_Y = 4 * pow(5, _Q - 2, _Q)


def _base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + _BASE58_ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def _base58_encode(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    chars: list[str] = []
    while number:
        number, remainder = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[remainder])
    return _BASE58_ALPHABET[0] * (len(value) - len(value.lstrip(b"\x00"))) + (
        "".join(reversed(chars)) or _BASE58_ALPHABET[0]
    )


def _recover_x(y: int) -> int:
    xx = ((y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q)) % _Q
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x & 1:
        x = _Q - x
    return x


def _decode_point(value: bytes) -> tuple[int, int]:
    if len(value) != 32:
        raise ValueError("Ed25519 point must be 32 bytes")
    y = int.from_bytes(value, "little") & ((1 << 255) - 1)
    x = _recover_x(y)
    if (x & 1) != (value[31] >> 7):
        x = _Q - x
    if (y * y - x * x - 1 - _D * x * x * y * y) % _Q != 0:
        raise ValueError("invalid Ed25519 point")
    return x, y


def _add_points(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    denominator_x = (1 + _D * x1 * x2 * y1 * y2) % _Q
    denominator_y = (1 - _D * x1 * x2 * y1 * y2) % _Q
    x3 = ((x1 * y2 + x2 * y1) * pow(denominator_x, _Q - 2, _Q)) % _Q
    y3 = ((y1 * y2 + x1 * x2) * pow(denominator_y, _Q - 2, _Q)) % _Q
    return x3, y3


def _multiply(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _add_points(result, addend)
        addend = _add_points(addend, addend)
        scalar >>= 1
    return result


def _base_point() -> tuple[int, int]:
    x = _recover_x(_B_Y)
    if x & 1:
        x = _Q - x
    return x, _B_Y


def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    scalar = int.from_bytes(signature[32:], "little")
    if scalar >= _L:
        return False
    try:
        public_point = _decode_point(public_key)
        signature_point = _decode_point(signature[:32])
    except ValueError:
        return False
    digest = hashlib.sha512(signature[:32] + public_key + message).digest()
    challenge = int.from_bytes(digest, "little") % _L
    return _multiply(_base_point(), scalar) == _add_points(
        signature_point, _multiply(public_point, challenge)
    )


def _signed_request(response: QuoteResponse) -> dict[str, Any]:
    request = response.quote_request
    payload: dict[str, Any] = {
        "dry": request.dry,
        "swapType": request.swap_type,
        "slippageTolerance": request.slippage_tolerance,
        "originAsset": request.origin_asset,
        "depositType": request.deposit_type,
        "destinationAsset": request.destination_asset,
        "amount": request.amount,
        "refundTo": request.refund_to,
        "refundType": request.refund_type,
        "recipient": request.recipient,
        "recipientType": request.recipient_type,
        "deadline": request.deadline,
    }
    optional = {
        "quoteWaitingTimeMs": request.quote_waiting_time_ms,
        "referral": request.referral,
        "virtualChainRecipient": request.virtual_chain_recipient,
        "virtualChainRefundRecipient": request.virtual_chain_refund_recipient,
        "customRecipientMsg": request.custom_recipient_msg,
    }
    payload.update({key: value for key, value in optional.items() if value})
    return payload


def _signed_quote(response: QuoteResponse) -> dict[str, Any]:
    quote = response.quote
    payload: dict[str, Any] = {
        "amountIn": quote.amount_in,
        "amountInFormatted": quote.amount_in_formatted,
        "amountInUsd": quote.amount_in_usd,
        "minAmountIn": quote.min_amount_in,
        "amountOut": quote.amount_out,
        "amountOutFormatted": quote.amount_out_formatted,
        "amountOutUsd": quote.amount_out_usd,
        "minAmountOut": quote.min_amount_out,
    }
    if not response.quote_request.dry:
        optional = {
            "depositAddress": quote.deposit_address,
            "depositMemo": quote.deposit_memo,
            "deadline": quote.deadline,
            "timeWhenInactive": quote.time_when_inactive,
            "timeEstimate": quote.time_estimate,
            "refundFee": quote.refund_fee,
            "withdrawFee": quote.withdraw_fee,
        }
        payload.update({key: value for key, value in optional.items() if value})
    return payload


def quote_hash(response: QuoteResponse) -> str:
    payload = {
        **_signed_request(response),
        **_signed_quote(response),
        "timestamp": response.timestamp,
    }
    stable = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _base58_encode(hashlib.sha256(stable).digest())


def verify_ed25519_signature(public_key: str, signature: str, message: bytes) -> bool:
    try:
        public_key_bytes = _base58_decode(public_key.removeprefix("ed25519:"))
        signature_bytes = _base58_decode(signature.removeprefix("ed25519:"))
        return _verify_ed25519(public_key_bytes, signature_bytes, message)
    except (ValueError, IndexError, TypeError):
        return False


def verify_quote_signature(
    response: QuoteResponse,
    public_key: str = TIDEPOOL_MAKER_PUBLIC_KEY,
) -> bool:
    return verify_ed25519_signature(
        public_key,
        response.signature,
        quote_hash(response).encode("utf-8"),
    )
