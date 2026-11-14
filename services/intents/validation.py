"""Validation and exact base-unit helpers for S4 funding quotes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from services.trend_radar.models import iso_utc, parse_iso

from .config import IntentsConfig
from .signature import verify_quote_signature
from .models import (
    DESTINATION_ASSET,
    DepositMode,
    DepositType,
    QuoteRequest,
    QuoteResponse,
    RecipientType,
    RefundType,
    SwapType,
    Token,
)


NEAR_ACCOUNT_RE = re.compile(r"^(?:[a-z0-9][a-z0-9._-]{1,62}[a-z0-9]|[0-9a-f]{64})$")
BASE58_SIGNATURE_RE = re.compile(r"^ed25519:[1-9A-HJ-NP-Za-km-z]{80,100}$")
EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
STELLAR_ADDRESS_RE = re.compile(r"^G[A-Z2-7]{55}$")
SUI_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
XRP_ADDRESS_RE = re.compile(r"^r[1-9A-HJ-NP-Za-km-z]{24,34}$")
BITCOIN_ADDRESS_RE = re.compile(r"^(?:bc1|tb1)[a-z0-9]{11,87}$|^[mn2][1-9A-HJ-NP-Za-km-z]{25,39}$")
INTEGER_RE = re.compile(r"^[0-9]+$")


class ValidationError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "field": self.field}


@dataclass(frozen=True)
class Route:
    source: Token
    destination: Token

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "destination": self.destination.to_dict(),
            "label": f"{self.source.symbol} ({self.source.blockchain}) -> {self.destination.symbol}",
        }


@dataclass(frozen=True)
class QuoteValidation:
    route: Route
    expires_at: datetime
    implied_fee_usd: str
    warnings: list[str]
    signature_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.to_dict(),
            "expires_at": iso_utc(self.expires_at),
            "implied_fee_usd": self.implied_fee_usd,
            "warnings": self.warnings,
            "signature_verified": self.signature_verified,
        }


def is_near_account(value: str) -> bool:
    return bool(NEAR_ACCOUNT_RE.fullmatch(value or ""))


def is_valid_signature_shape(value: str) -> bool:
    return bool(BASE58_SIGNATURE_RE.fullmatch(value or ""))


def is_valid_refund_address(value: str, blockchain: str) -> bool:
    """Validate a user-controlled refund address for the selected origin chain."""
    if blockchain == "near":
        return is_near_account(value)
    if blockchain in {"base", "arb", "eth", "bsc", "aurora", "hypercore"}:
        return bool(EVM_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "sol":
        return bool(SOLANA_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "stellar":
        return bool(STELLAR_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "sui":
        return bool(SUI_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "xrp":
        return bool(XRP_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "btc":
        return bool(BITCOIN_ADDRESS_RE.fullmatch(value or ""))
    return False


def is_valid_deposit_address(value: str, blockchain: str) -> bool:
    """Validate the provider address on the selected origin chain."""
    return is_valid_refund_address(value, blockchain)


def is_valid_deposit_tx_hash(value: str, blockchain: str) -> bool:
    """Validate a user-submitted transaction reference without accepting a route mismatch."""
    if blockchain == "near":
        return bool(value and len(value) >= 2)
    if blockchain in {"base", "arb", "eth", "bsc", "aurora", "hypercore"}:
        return bool(re.fullmatch(r"0x[0-9a-fA-F]{64}", value or ""))
    if blockchain == "sol":
        return bool(SOLANA_ADDRESS_RE.fullmatch(value or ""))
    if blockchain == "stellar":
        return bool(re.fullmatch(r"[0-9a-fA-F]{64}", value or ""))
    if blockchain == "sui":
        return bool(re.fullmatch(r"0x[0-9a-fA-F]{64}", value or ""))
    if blockchain == "btc":
        return bool(re.fullmatch(r"[0-9a-fA-F]{64}", value or ""))
    return False


def parse_base_units(value: str, *, field: str = "amount") -> int:
    if not isinstance(value, str) or not INTEGER_RE.fullmatch(value):
        raise ValidationError(
            "INVALID_AMOUNT",
            f"{field} must be an integer string in base units",
            field=field,
        )
    amount = int(value)
    if amount <= 0:
        raise ValidationError("INVALID_AMOUNT", f"{field} must be greater than zero", field=field)
    return amount


def format_base_units(value: str | int, decimals: int) -> str:
    amount = int(value)
    scale = Decimal(10) ** int(decimals)
    rendered = (Decimal(amount) / scale).quantize(Decimal(1).scaleb(-int(decimals)))
    text = format(rendered, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def usd_value(amount: str | int, token: Token) -> Decimal:
    try:
        return (Decimal(int(amount)) / (Decimal(10) ** token.decimals)) * Decimal(str(token.price))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("INVALID_AMOUNT", "amount cannot be priced", field="amount") from exc


def select_route(
    tokens: list[Token],
    source_asset: str,
    config: IntentsConfig,
    *,
    source_chain: str | None = None,
) -> Route:
    by_id = {token.asset_id: token for token in tokens}
    source = by_id.get(source_asset)
    destination = by_id.get(config.destination_asset)
    if source is None:
        raise ValidationError(
            "UNSUPPORTED_SOURCE_ASSET",
            f"source asset is not in the live /v0/tokens list: {source_asset}",
            field="originAsset",
        )
    if destination is None:
        raise ValidationError(
            "DESTINATION_ASSET_UNAVAILABLE",
            f"destination asset is not in the live /v0/tokens list: {config.destination_asset}",
            field="destinationAsset",
        )
    if destination.asset_id != DESTINATION_ASSET:
        raise ValidationError(
            "WRONG_DESTINATION",
            f"destination must be {DESTINATION_ASSET}",
            field="destinationAsset",
        )
    if source.asset_id == destination.asset_id:
        raise ValidationError(
            "SAME_ASSET",
            "source and destination assets must differ",
            field="originAsset",
        )
    expected_chain = source_chain or config.source_chain
    if expected_chain == "external":
        if source.blockchain == "near":
            raise ValidationError(
                "UNSUPPORTED_SOURCE_CHAIN",
                "initial funding route requires an external testnet source chain",
                field="originAsset",
            )
    elif source.blockchain != expected_chain:
        raise ValidationError(
            "UNSUPPORTED_SOURCE_CHAIN",
            f"initial funding route supports {expected_chain} only; got {source.blockchain}",
            field="originAsset",
        )
    if destination.blockchain != "near":
        raise ValidationError(
            "UNSUPPORTED_DESTINATION_CHAIN",
            "destination collateral must be a NEAR NEP-141 token",
            field="destinationAsset",
        )
    return Route(source=source, destination=destination)


def supported_routes(
    tokens: list[Token],
    config: IntentsConfig,
    *,
    source_chain: str | None = None,
) -> list[Route]:
    destination = next((t for t in tokens if t.asset_id == config.destination_asset), None)
    if destination is None:
        return []
    expected_chain = source_chain or config.source_chain
    return [
        Route(source=token, destination=destination)
        for token in tokens
        if token.asset_id != destination.asset_id
        and (token.blockchain != "near" if expected_chain == "external" else token.blockchain == expected_chain)
    ]


def validate_request(
    request: QuoteRequest,
    tokens: list[Token],
    config: IntentsConfig,
    *,
    now: datetime,
    source_chain: str | None = None,
) -> Route:
    if request.destination_asset != config.destination_asset:
        raise ValidationError(
            "WRONG_DESTINATION",
            f"destination must be {config.destination_asset}",
            field="destinationAsset",
        )
    if request.swap_type != SwapType.EXACT_INPUT.value:
        raise ValidationError(
            "UNSUPPORTED_SWAP_TYPE",
            "initial funding integration supports EXACT_INPUT only",
            field="swapType",
        )
    if not (0 < int(request.slippage_tolerance) <= config.max_slippage_bps):
        raise ValidationError(
            "INVALID_SLIPPAGE",
            f"slippageTolerance must be between 1 and {config.max_slippage_bps} bps",
            field="slippageTolerance",
        )
    if request.deposit_type not in {
        DepositType.ORIGIN_CHAIN.value,
        DepositType.INTENTS.value,
    }:
        raise ValidationError(
            "UNSUPPORTED_DEPOSIT_TYPE",
            "depositType must be ORIGIN_CHAIN or INTENTS",
            field="depositType",
        )
    if request.refund_type not in {
        RefundType.ORIGIN_CHAIN.value,
        RefundType.INTENTS.value,
    }:
        raise ValidationError(
            "UNSUPPORTED_REFUND_TYPE",
            "refundType must be ORIGIN_CHAIN or INTENTS",
            field="refundType",
        )
    if request.recipient_type != RecipientType.DESTINATION_CHAIN.value:
        raise ValidationError(
            "UNSUPPORTED_RECIPIENT_TYPE",
            "recipientType must be DESTINATION_CHAIN for wallet collateral",
            field="recipientType",
        )
    if request.deposit_mode not in {mode.value for mode in DepositMode}:
        raise ValidationError(
            "UNSUPPORTED_DEPOSIT_MODE",
            "depositMode must be SIMPLE or MEMO",
            field="depositMode",
        )
    if not is_near_account(request.recipient):
        raise ValidationError(
            "INVALID_RECIPIENT",
            "recipient must be a NEAR testnet account",
            field="recipient",
        )
    route = select_route(tokens, request.origin_asset, config, source_chain=source_chain)
    expected_refund_type = (
        RefundType.ORIGIN_CHAIN.value
        if request.deposit_type == DepositType.ORIGIN_CHAIN.value
        else RefundType.INTENTS.value
    )
    if request.refund_type != expected_refund_type:
        raise ValidationError(
            "UNSUPPORTED_REFUND_TYPE",
            f"refundType must be {expected_refund_type} for depositType {request.deposit_type}",
            field="refundType",
        )
    if not is_valid_refund_address(request.refund_to, route.source.blockchain):
        raise ValidationError(
            "INVALID_REFUND_TO",
            f"refundTo is not a valid {route.source.blockchain} testnet address",
            field="refundTo",
        )
    amount = parse_base_units(request.amount)
    usd = usd_value(amount, route.source)
    if usd < Decimal(str(config.min_amount_usd)):
        raise ValidationError(
            "AMOUNT_BELOW_MINIMUM",
            f"amount is below the configured minimum of {config.min_amount_usd} USD",
            field="amount",
        )
    if usd > Decimal(str(config.max_amount_usd)):
        raise ValidationError(
            "AMOUNT_ABOVE_MAXIMUM",
            f"amount is above the configured maximum of {config.max_amount_usd} USD",
            field="amount",
        )
    deadline = parse_iso(request.deadline)
    if deadline is None:
        raise ValidationError("INVALID_DEADLINE", "deadline must be ISO-8601", field="deadline")
    if deadline <= now:
        raise ValidationError("QUOTE_EXPIRED", "deadline is not in the future", field="deadline")
    if (deadline - now).total_seconds() > config.max_quote_ttl_seconds:
        raise ValidationError(
            "DEADLINE_TOO_FAR",
            f"deadline must be within {config.max_quote_ttl_seconds} seconds",
            field="deadline",
        )
    return route


def validate_quote_response(
    response: QuoteResponse,
    request: QuoteRequest,
    route: Route,
    config: IntentsConfig,
    *,
    now: datetime,
    verify_signature: bool = False,
) -> QuoteValidation:
    echoed = response.quote_request
    checks = {
        "originAsset": (echoed.origin_asset, request.origin_asset),
        "destinationAsset": (echoed.destination_asset, request.destination_asset),
        "amount": (echoed.amount, request.amount),
        "depositType": (echoed.deposit_type, request.deposit_type),
        "refundType": (echoed.refund_type, request.refund_type),
        "refundTo": (echoed.refund_to, request.refund_to),
        "recipient": (echoed.recipient, request.recipient),
        "recipientType": (echoed.recipient_type, request.recipient_type),
        "swapType": (echoed.swap_type, request.swap_type),
    }
    for field, (actual, expected) in checks.items():
        if actual != expected:
            raise ValidationError(
                "QUOTE_ECHO_MISMATCH",
                f"provider echoed {field}={actual!r}, expected {expected!r}",
                field=field,
            )
    if not response.correlation_id:
        raise ValidationError("MISSING_QUOTE_ID", "provider quote has no correlationId")
    if not is_valid_signature_shape(response.signature):
        raise ValidationError(
            "INVALID_QUOTE_SIGNATURE",
            "provider quote signature is not ed25519 base58",
            field="signature",
        )
    signature_verified = False
    if verify_signature:
        if not verify_quote_signature(response):
            raise ValidationError(
                "INVALID_QUOTE_SIGNATURE",
                "provider quote signature does not verify against Tidepool's maker key",
                field="signature",
            )
        signature_verified = True
    quote = response.quote
    amount_in = parse_base_units(quote.amount_in, field="amountIn")
    request_amount = parse_base_units(request.amount)
    if amount_in != request_amount:
        raise ValidationError(
            "AMOUNT_IN_MISMATCH",
            f"quote amountIn {amount_in} does not equal requested amount {request_amount}",
            field="amountIn",
        )
    min_amount_in = parse_base_units(quote.min_amount_in, field="minAmountIn")
    if min_amount_in > amount_in:
        raise ValidationError(
            "INVALID_MIN_AMOUNT_IN",
            "minAmountIn exceeds amountIn",
            field="minAmountIn",
        )
    amount_out = parse_base_units(quote.amount_out, field="amountOut")
    min_amount_out = parse_base_units(quote.min_amount_out, field="minAmountOut")
    if min_amount_out > amount_out:
        raise ValidationError(
            "INVALID_MIN_AMOUNT_OUT",
            "minAmountOut exceeds amountOut",
            field="minAmountOut",
        )
    if request.dry:
        if quote.deposit_address:
            raise ValidationError(
                "DRY_QUOTE_HAS_DEPOSIT_ADDRESS",
                "dry quote unexpectedly contains a deposit address",
                field="depositAddress",
            )
        expires_at = parse_iso(request.deadline)
    else:
        if not quote.deposit_address:
            raise ValidationError(
                "MISSING_DEPOSIT_ADDRESS",
                "live quote has no deposit address",
                field="depositAddress",
            )
        if not is_valid_deposit_address(quote.deposit_address, route.source.blockchain):
            raise ValidationError(
                "INVALID_DEPOSIT_ADDRESS",
                f"live quote deposit address is not a valid {route.source.blockchain} address",
                field="depositAddress",
            )
        expires_at = parse_iso(quote.deadline) or parse_iso(request.deadline)
        if expires_at is None or expires_at <= now:
            raise ValidationError(
                "QUOTE_EXPIRED",
                "live quote deadline has passed",
                field="deadline",
            )
    if request.deposit_mode == DepositMode.MEMO.value and not quote.deposit_memo:
        raise ValidationError(
            "MISSING_DEPOSIT_MEMO",
            "depositMode=MEMO requires a deposit memo",
            field="depositMemo",
        )
    try:
        implied_fee = Decimal(quote.amount_in_usd) - Decimal(quote.amount_out_usd)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(
            "INVALID_QUOTE_USD",
            "quote USD values are not decimal strings",
        ) from exc
    warnings: list[str] = []
    if quote.deposit_memo:
        warnings.append("Provider requires deposit memo; preserve it exactly.")
    if route.source.asset_id != route.destination.asset_id:
        warnings.append("Testnet-only swap; tokens have no value.")
    if expires_at is None:
        raise ValidationError("INVALID_DEADLINE", "quote has no usable expiry", field="deadline")
    return QuoteValidation(
        route=route,
        expires_at=expires_at,
        implied_fee_usd=format(implied_fee, "f"),
        warnings=warnings,
        signature_verified=signature_verified,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
