"""Typed models for the Tidepool / 1Click testnet funding adapter (S4).

The provider is a 1Click-compatible testnet sandbox.  All amounts are integer
strings in base units; no float is used for money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from services.trend_radar.models import iso_utc, parse_iso


DESTINATION_ASSET = "nep141:usdc.tidepool-sandbox.testnet"
DESTINATION_SYMBOL = "USDC"
DEFAULT_VERIFIER_ACCOUNT = "verifier.tidepool-sandbox.testnet"
DEFAULT_MARKET_CONTRACT = "market.notch-dev.testnet"
DEFAULT_RPC_URL = "https://rpc.testnet.near.org"
DEFAULT_BASE_URL = "https://www.usetidepool.tech"
SCHEMA_VERSION = "notch.intents.funding/1"


class FundingState(str, Enum):
    IDLE = "IDLE"
    QUOTED = "QUOTED"
    AWAITING_DEPOSIT = "AWAITING_DEPOSIT"
    DEPOSIT_DETECTED = "DEPOSIT_DETECTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


TERMINAL_STATES = {
    FundingState.SUCCESS,
    FundingState.REFUNDED,
    FundingState.FAILED,
    FundingState.EXPIRED,
}


class ProviderStatus(str, Enum):
    KNOWN_DEPOSIT_TX = "KNOWN_DEPOSIT_TX"
    PENDING_DEPOSIT = "PENDING_DEPOSIT"
    INCOMPLETE_DEPOSIT = "INCOMPLETE_DEPOSIT"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class DepositType(str, Enum):
    ORIGIN_CHAIN = "ORIGIN_CHAIN"
    INTENTS = "INTENTS"


class RefundType(str, Enum):
    ORIGIN_CHAIN = "ORIGIN_CHAIN"
    INTENTS = "INTENTS"


class RecipientType(str, Enum):
    DESTINATION_CHAIN = "DESTINATION_CHAIN"
    INTENTS = "INTENTS"


class SwapType(str, Enum):
    EXACT_INPUT = "EXACT_INPUT"
    EXACT_OUTPUT = "EXACT_OUTPUT"
    FLEX_INPUT = "FLEX_INPUT"


class DepositMode(str, Enum):
    SIMPLE = "SIMPLE"
    MEMO = "MEMO"


@dataclass(frozen=True)
class Token:
    asset_id: str
    decimals: int
    blockchain: str
    symbol: str
    price: float
    price_updated_at: str | None = None
    contract_address: str | None = None
    coingecko_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any]) -> "Token":
        required = ("assetId", "decimals", "blockchain", "symbol", "price")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"token missing fields: {', '.join(missing)}")
        return cls(
            asset_id=str(data["assetId"]),
            decimals=int(data["decimals"]),
            blockchain=str(data["blockchain"]),
            symbol=str(data["symbol"]),
            price=float(data["price"]),
            price_updated_at=data.get("priceUpdatedAt"),
            contract_address=data.get("contractAddress"),
            coingecko_id=data.get("coingeckoId"),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "decimals": self.decimals,
            "blockchain": self.blockchain,
            "symbol": self.symbol,
            "price": self.price,
            "price_updated_at": self.price_updated_at,
            "contract_address": self.contract_address,
            "coingecko_id": self.coingecko_id,
        }


@dataclass(frozen=True)
class QuoteRequest:
    dry: bool
    swap_type: str
    slippage_tolerance: int
    origin_asset: str
    deposit_type: str
    destination_asset: str
    amount: str
    refund_to: str
    refund_type: str
    recipient: str
    recipient_type: str
    deadline: str
    deposit_mode: str = DepositMode.SIMPLE.value
    quote_waiting_time_ms: int | None = None
    referral: str | None = None
    virtual_chain_recipient: str | None = None
    virtual_chain_refund_recipient: str | None = None
    custom_recipient_msg: str | None = None

    def to_provider_dict(self) -> dict[str, Any]:
        """Return exactly the fields accepted by POST /v0/quote."""
        body: dict[str, Any] = {
            "dry": self.dry,
            "swapType": self.swap_type,
            "slippageTolerance": self.slippage_tolerance,
            "originAsset": self.origin_asset,
            "depositType": self.deposit_type,
            "destinationAsset": self.destination_asset,
            "amount": self.amount,
            "refundTo": self.refund_to,
            "refundType": self.refund_type,
            "recipient": self.recipient,
            "recipientType": self.recipient_type,
            "deadline": self.deadline,
        }
        if self.deposit_mode:
            body["depositMode"] = self.deposit_mode
        if self.quote_waiting_time_ms is not None:
            body["quoteWaitingTimeMs"] = self.quote_waiting_time_ms
        if self.referral:
            body["referral"] = self.referral
        if self.virtual_chain_recipient:
            body["virtualChainRecipient"] = self.virtual_chain_recipient
        if self.virtual_chain_refund_recipient:
            body["virtualChainRefundRecipient"] = self.virtual_chain_refund_recipient
        if self.custom_recipient_msg:
            body["customRecipientMsg"] = self.custom_recipient_msg
        return body

    def to_dict(self) -> dict[str, Any]:
        return self.to_provider_dict()


@dataclass(frozen=True)
class Quote:
    amount_in: str
    amount_in_formatted: str
    amount_in_usd: str
    min_amount_in: str
    amount_out: str
    amount_out_formatted: str
    amount_out_usd: str
    min_amount_out: str
    time_estimate: int
    deposit_address: str | None = None
    deposit_memo: str | None = None
    deadline: str | None = None
    time_when_inactive: str | None = None
    refund_fee: str | None = None
    withdraw_fee: str | None = None
    chain_deposit_addresses: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any]) -> "Quote":
        required = (
            "amountIn",
            "amountInFormatted",
            "amountInUsd",
            "minAmountIn",
            "amountOut",
            "amountOutFormatted",
            "amountOutUsd",
            "minAmountOut",
            "timeEstimate",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"quote missing fields: {', '.join(missing)}")
        return cls(
            amount_in=str(data["amountIn"]),
            amount_in_formatted=str(data["amountInFormatted"]),
            amount_in_usd=str(data["amountInUsd"]),
            min_amount_in=str(data["minAmountIn"]),
            amount_out=str(data["amountOut"]),
            amount_out_formatted=str(data["amountOutFormatted"]),
            amount_out_usd=str(data["amountOutUsd"]),
            min_amount_out=str(data["minAmountOut"]),
            time_estimate=int(data["timeEstimate"]),
            deposit_address=data.get("depositAddress"),
            deposit_memo=data.get("depositMemo"),
            deadline=data.get("deadline"),
            time_when_inactive=data.get("timeWhenInactive"),
            refund_fee=data.get("refundFee"),
            withdraw_fee=data.get("withdrawFee"),
            chain_deposit_addresses=list(data.get("chainDepositAddresses") or []),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount_in": self.amount_in,
            "amount_in_formatted": self.amount_in_formatted,
            "amount_in_usd": self.amount_in_usd,
            "min_amount_in": self.min_amount_in,
            "amount_out": self.amount_out,
            "amount_out_formatted": self.amount_out_formatted,
            "amount_out_usd": self.amount_out_usd,
            "min_amount_out": self.min_amount_out,
            "time_estimate": self.time_estimate,
            "deposit_address": self.deposit_address,
            "deposit_memo": self.deposit_memo,
            "deadline": self.deadline,
            "time_when_inactive": self.time_when_inactive,
            "refund_fee": self.refund_fee,
            "withdraw_fee": self.withdraw_fee,
            "chain_deposit_addresses": self.chain_deposit_addresses,
        }


@dataclass(frozen=True)
class QuoteResponse:
    correlation_id: str
    timestamp: str
    signature: str
    quote_request: QuoteRequest
    quote: Quote
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any]) -> "QuoteResponse":
        for key in ("correlationId", "timestamp", "signature", "quoteRequest", "quote"):
            if key not in data:
                raise ValueError(f"quote response missing {key}")
        request_data = data["quoteRequest"]
        request = QuoteRequest(
            dry=bool(request_data.get("dry")),
            swap_type=str(request_data.get("swapType")),
            slippage_tolerance=int(request_data.get("slippageTolerance", 0)),
            origin_asset=str(request_data.get("originAsset")),
            deposit_type=str(request_data.get("depositType")),
            destination_asset=str(request_data.get("destinationAsset")),
            amount=str(request_data.get("amount")),
            refund_to=str(request_data.get("refundTo")),
            refund_type=str(request_data.get("refundType")),
            recipient=str(request_data.get("recipient")),
            recipient_type=str(request_data.get("recipientType")),
            deadline=str(request_data.get("deadline")),
            deposit_mode=str(request_data.get("depositMode") or DepositMode.SIMPLE.value),
            quote_waiting_time_ms=request_data.get("quoteWaitingTimeMs"),
            referral=request_data.get("referral"),
            virtual_chain_recipient=request_data.get("virtualChainRecipient"),
            virtual_chain_refund_recipient=request_data.get("virtualChainRefundRecipient"),
            custom_recipient_msg=request_data.get("customRecipientMsg"),
        )
        return cls(
            correlation_id=str(data["correlationId"]),
            timestamp=str(data["timestamp"]),
            signature=str(data["signature"]),
            quote_request=request,
            quote=Quote.from_provider(data["quote"]),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "quote_request": self.quote_request.to_dict(),
            "quote": self.quote.to_dict(),
        }


@dataclass(frozen=True)
class SwapDetails:
    intent_hashes: list[str] = field(default_factory=list)
    near_tx_hashes: list[str] = field(default_factory=list)
    origin_chain_tx_hashes: list[dict[str, Any]] = field(default_factory=list)
    destination_chain_tx_hashes: list[dict[str, Any]] = field(default_factory=list)
    amount_in: str | None = None
    amount_in_formatted: str | None = None
    amount_in_usd: str | None = None
    amount_out: str | None = None
    amount_out_formatted: str | None = None
    amount_out_usd: str | None = None
    slippage: float | None = None
    refunded_amount: str | None = None
    refunded_amount_formatted: str | None = None
    refunded_amount_usd: str | None = None
    refund_reason: str | None = None
    deposited_amount: str | None = None
    deposited_amount_formatted: str | None = None
    deposited_amount_usd: str | None = None
    withdraw_fee: str | None = None
    referral: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any] | None) -> "SwapDetails":
        data = data or {}
        return cls(
            intent_hashes=list(data.get("intentHashes") or []),
            near_tx_hashes=list(data.get("nearTxHashes") or []),
            origin_chain_tx_hashes=list(data.get("originChainTxHashes") or []),
            destination_chain_tx_hashes=list(data.get("destinationChainTxHashes") or []),
            amount_in=data.get("amountIn"),
            amount_in_formatted=data.get("amountInFormatted"),
            amount_in_usd=data.get("amountInUsd"),
            amount_out=data.get("amountOut"),
            amount_out_formatted=data.get("amountOutFormatted"),
            amount_out_usd=data.get("amountOutUsd"),
            slippage=data.get("slippage"),
            refunded_amount=data.get("refundedAmount"),
            refunded_amount_formatted=data.get("refundedAmountFormatted"),
            refunded_amount_usd=data.get("refundedAmountUsd"),
            refund_reason=data.get("refundReason"),
            deposited_amount=data.get("depositedAmount"),
            deposited_amount_formatted=data.get("depositedAmountFormatted"),
            deposited_amount_usd=data.get("depositedAmountUsd"),
            withdraw_fee=data.get("withdrawFee"),
            referral=data.get("referral"),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_hashes": self.intent_hashes,
            "near_tx_hashes": self.near_tx_hashes,
            "origin_chain_tx_hashes": self.origin_chain_tx_hashes,
            "destination_chain_tx_hashes": self.destination_chain_tx_hashes,
            "amount_in": self.amount_in,
            "amount_in_formatted": self.amount_in_formatted,
            "amount_in_usd": self.amount_in_usd,
            "amount_out": self.amount_out,
            "amount_out_formatted": self.amount_out_formatted,
            "amount_out_usd": self.amount_out_usd,
            "slippage": self.slippage,
            "refunded_amount": self.refunded_amount,
            "refunded_amount_formatted": self.refunded_amount_formatted,
            "refunded_amount_usd": self.refunded_amount_usd,
            "refund_reason": self.refund_reason,
            "deposited_amount": self.deposited_amount,
            "deposited_amount_formatted": self.deposited_amount_formatted,
            "deposited_amount_usd": self.deposited_amount_usd,
            "withdraw_fee": self.withdraw_fee,
            "referral": self.referral,
        }


@dataclass(frozen=True)
class StatusResponse:
    correlation_id: str
    quote_response: QuoteResponse
    status: str
    updated_at: str
    swap_details: SwapDetails
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_provider(cls, data: dict[str, Any]) -> "StatusResponse":
        for key in ("correlationId", "quoteResponse", "status", "updatedAt", "swapDetails"):
            if key not in data:
                raise ValueError(f"status response missing {key}")
        return cls(
            correlation_id=str(data["correlationId"]),
            quote_response=QuoteResponse.from_provider(data["quoteResponse"]),
            status=str(data["status"]),
            updated_at=str(data["updatedAt"]),
            swap_details=SwapDetails.from_provider(data.get("swapDetails")),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "quote_response": self.quote_response.to_dict(),
            "status": self.status,
            "updated_at": self.updated_at,
            "swap_details": self.swap_details.to_dict(),
        }


@dataclass(frozen=True)
class DepositStep:
    step: int
    action: str
    contract: str
    method: str
    args: dict[str, Any]
    gas_tgas: int
    attached_deposit_yocto: str
    note: str


@dataclass(frozen=True)
class DepositInstructions:
    quote_id: str
    source_chain: str
    source_asset: str
    source_symbol: str
    source_decimals: int
    destination_asset: str
    destination_symbol: str
    destination_decimals: int
    amount_in: str
    min_amount_out: str
    deposit_type: str
    provider_deposit_address: str
    deposit_memo: str | None
    recipient: str
    refund_to: str
    deadline: str | None
    steps: list[DepositStep]
    warnings: list[str]
    supported: bool = True
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "source_chain": self.source_chain,
            "source_asset": self.source_asset,
            "source_symbol": self.source_symbol,
            "source_decimals": self.source_decimals,
            "destination_asset": self.destination_asset,
            "destination_symbol": self.destination_symbol,
            "destination_decimals": self.destination_decimals,
            "amount_in": self.amount_in,
            "min_amount_out": self.min_amount_out,
            "deposit_type": self.deposit_type,
            "provider_deposit_address": self.provider_deposit_address,
            "deposit_memo": self.deposit_memo,
            "recipient": self.recipient,
            "refund_to": self.refund_to,
            "deadline": self.deadline,
            "supported": self.supported,
            "blocker": self.blocker,
            "steps": [
                {
                    "step": step.step,
                    "action": step.action,
                    "contract": step.contract,
                    "method": step.method,
                    "args": step.args,
                    "gas_tgas": step.gas_tgas,
                    "attached_deposit_yocto": step.attached_deposit_yocto,
                    "note": step.note,
                }
                for step in self.steps
            ],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class BalanceCheck:
    account: str
    asset_id: str
    before: str
    after: str
    delta: str
    required: str
    verified: bool
    checked_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "asset_id": self.asset_id,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "required": self.required,
            "verified": self.verified,
            "checked_at": self.checked_at,
            "error": self.error,
        }


@dataclass
class FundingQuote:
    quote_id: str
    correlation_id: str
    state: FundingState
    dry: bool
    source_asset: str
    source_symbol: str
    source_chain: str
    source_decimals: int
    destination_asset: str
    destination_symbol: str
    destination_decimals: int
    amount_in: str
    amount_out: str
    min_amount_out: str
    slippage_bps: int
    recipient: str
    refund_to: str
    deposit_type: str
    refund_type: str
    deadline: str | None
    deposit_address: str | None
    deposit_memo: str | None
    signature: str
    quote_timestamp: str
    created_at: str
    updated_at: str
    balance_before: str | None = None
    balance_after: str | None = None
    balance_delta: str | None = None
    balance_verified: bool = False
    provider_status: str | None = None
    deposit_tx_hash: str | None = None
    deposit_submitted: bool = False
    deposit_recorded_at: str | None = None
    last_error: str | None = None
    refund_tx_hash: str | None = None
    refund_reason: str | None = None
    refunded_amount: str | None = None
    poll_count: int = 0
    expires_at: str | None = None
    raw_quote: dict[str, Any] = field(default_factory=dict)
    raw_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "quote_id": self.quote_id,
            "correlation_id": self.correlation_id,
            "state": self.state.value,
            "dry": self.dry,
            "source_asset": self.source_asset,
            "source_symbol": self.source_symbol,
            "source_chain": self.source_chain,
            "source_decimals": self.source_decimals,
            "destination_asset": self.destination_asset,
            "destination_symbol": self.destination_symbol,
            "destination_decimals": self.destination_decimals,
            "amount_in": self.amount_in,
            "amount_out": self.amount_out,
            "min_amount_out": self.min_amount_out,
            "slippage_bps": self.slippage_bps,
            "recipient": self.recipient,
            "refund_to": self.refund_to,
            "deposit_type": self.deposit_type,
            "refund_type": self.refund_type,
            "deadline": self.deadline,
            "deposit_address": self.deposit_address,
            "deposit_memo": self.deposit_memo,
            "signature": self.signature,
            "quote_timestamp": self.quote_timestamp,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "balance_delta": self.balance_delta,
            "balance_verified": self.balance_verified,
            "provider_status": self.provider_status,
            "deposit_tx_hash": self.deposit_tx_hash,
            "deposit_submitted": self.deposit_submitted,
            "deposit_recorded_at": self.deposit_recorded_at,
            "last_error": self.last_error,
            "refund_tx_hash": self.refund_tx_hash,
            "refund_reason": self.refund_reason,
            "refunded_amount": self.refunded_amount,
            "poll_count": self.poll_count,
            "expires_at": self.expires_at,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Include provider bodies only for the private server-side store."""
        return {
            **self.to_dict(),
            "raw_quote": self.raw_quote,
            "raw_status": self.raw_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FundingQuote":
        return cls(
            quote_id=str(data["quote_id"]),
            correlation_id=str(data["correlation_id"]),
            state=FundingState(data["state"]),
            dry=bool(data["dry"]),
            source_asset=str(data["source_asset"]),
            source_symbol=str(data["source_symbol"]),
            source_chain=str(data["source_chain"]),
            source_decimals=int(data["source_decimals"]),
            destination_asset=str(data["destination_asset"]),
            destination_symbol=str(data["destination_symbol"]),
            destination_decimals=int(data["destination_decimals"]),
            amount_in=str(data["amount_in"]),
            amount_out=str(data["amount_out"]),
            min_amount_out=str(data["min_amount_out"]),
            slippage_bps=int(data["slippage_bps"]),
            recipient=str(data["recipient"]),
            refund_to=str(data["refund_to"]),
            deposit_type=str(data["deposit_type"]),
            refund_type=str(data["refund_type"]),
            deadline=data.get("deadline"),
            deposit_address=data.get("deposit_address"),
            deposit_memo=data.get("deposit_memo"),
            signature=str(data["signature"]),
            quote_timestamp=str(data["quote_timestamp"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            balance_before=data.get("balance_before"),
            balance_after=data.get("balance_after"),
            balance_delta=data.get("balance_delta"),
            balance_verified=bool(data.get("balance_verified")),
            provider_status=data.get("provider_status"),
            deposit_tx_hash=data.get("deposit_tx_hash"),
            deposit_submitted=bool(data.get("deposit_submitted")),
            deposit_recorded_at=data.get("deposit_recorded_at"),
            last_error=data.get("last_error"),
            refund_tx_hash=data.get("refund_tx_hash"),
            refund_reason=data.get("refund_reason"),
            refunded_amount=data.get("refunded_amount"),
            poll_count=int(data.get("poll_count", 0)),
            expires_at=data.get("expires_at"),
            raw_quote=dict(data.get("raw_quote") or {}),
            raw_status=dict(data.get("raw_status") or {}),
        )


def parse_utc(value: str | None) -> datetime | None:
    return parse_iso(value)


def utc_now_iso(value: datetime) -> str:
    return iso_utc(value) or ""
