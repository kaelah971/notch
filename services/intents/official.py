"""Official NEAR Intents 1Click Mainnet read-only integration.

This module is intentionally separate from the Tidepool Testnet funding
adapter.  It can discover Mainnet metadata and request dry quotes, but it
cannot create wet quotes, deposit instructions, submit deposits, or execute a
transaction.  Mainnet assets are never mapped to Notch's Testnet collateral.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from services.trend_radar.models import iso_utc, now_utc

from .client import RateLimiter, TidepoolClient, TidepoolError
from .models import (
    DepositMode,
    DepositType,
    FundingQuote,
    FundingState,
    QuoteRequest,
    QuoteResponse,
    RecipientType,
    RefundType,
    SwapType,
    Token,
)
from .signature import OFFICIAL_ONE_CLICK_MANAGER_PUBLIC_KEY
from .validation import (
    QuoteValidation,
    Route,
    ValidationError,
    select_route,
    validate_quote_response,
    validate_request,
)

OFFICIAL_ONECLICK_BASE_URL = "https://1click.chaindefuser.com"
OFFICIAL_PROVIDER_ID = "near-intents-1click-mainnet"
OFFICIAL_PROVIDER_LABEL = "Official NEAR Intents 1Click API"
OFFICIAL_NETWORK = "Mainnet"
OFFICIAL_ENVIRONMENT = "NOTCH_MAINNET_FUTURE"
# Observed from the official Mainnet /v0/tokens catalog; still revalidated live.
OFFICIAL_DEFAULT_DESTINATION_ASSET = "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"
OFFICIAL_FEE_NOTICE = (
    "Unauthenticated quotes incur the provider's documented additional 25 bps "
    "platform fee on non-ANY_INPUT routes. Configure a partner JWT for the "
    "authenticated fee schedule; the credential stays server-side."
)
MAINNET_EXECUTION_BLOCKERS = (
    "Notch's operational prediction market and collateral are NEAR Testnet-only.",
    "No independently verified Mainnet prediction contract and collateral configuration is enabled.",
    "Mainnet wallet authorization, reconciliation, finality, refund, and economic review are incomplete.",
)


def _is_mainnet_asset(value: str | None) -> bool:
    return bool(value) and ".testnet" not in value.lower()


def _is_mainnet_account(value: str | None) -> bool:
    return bool(value) and not value.lower().endswith(".testnet")


@dataclass(frozen=True)
class OfficialMainnetConfig:
    base_url: str = OFFICIAL_ONECLICK_BASE_URL
    api_key: str | None = None
    destination_asset: str | None = OFFICIAL_DEFAULT_DESTINATION_ASSET
    recipient: str | None = None
    refund_to: str | None = None
    source_chain: str = "external"
    min_amount_usd: float = 0.01
    max_amount_usd: float = 10.0
    default_slippage_bps: int = 100
    max_slippage_bps: int = 5_000
    quote_ttl_seconds: int = 900
    max_quote_ttl_seconds: int = 3_600
    request_timeout_seconds: float = 15.0
    max_retries: int = 2
    rate_limit_seconds: float = 0.25
    verify_quote_signatures: bool = True
    allow_dry_quotes: bool = True
    market_contract: str | None = None
    collateral_token: str | None = None

    def __post_init__(self) -> None:
        host = (self.base_url.split("://", 1)[-1].split("/", 1)[0]).lower()
        if host != "1click.chaindefuser.com":
            raise ValueError(
                "official Mainnet funding must use https://1click.chaindefuser.com"
            )
        if not self.base_url.startswith("https://"):
            raise ValueError("official Mainnet funding requires HTTPS")
        for label, value in (
            ("destination_asset", self.destination_asset),
            ("market_contract", self.market_contract),
            ("collateral_token", self.collateral_token),
        ):
            if value and not _is_mainnet_asset(value):
                raise ValueError(f"{label} cannot be a Testnet identifier")
        if self.recipient and not _is_mainnet_account(self.recipient):
            raise ValueError("Mainnet recipient cannot be a .testnet account")
        if self.quote_ttl_seconds < 60 or self.quote_ttl_seconds > self.max_quote_ttl_seconds:
            raise ValueError("Mainnet quote TTL is outside the bounded range")

    @classmethod
    def from_env(cls) -> "OfficialMainnetConfig":
        return cls(
            base_url=os.environ.get("NEAR_INTENTS_BASE_URL", OFFICIAL_ONECLICK_BASE_URL),
            api_key=os.environ.get("NEAR_INTENTS_API_KEY") or None,
            destination_asset=os.environ.get("NEAR_INTENTS_DESTINATION_ASSET") or OFFICIAL_DEFAULT_DESTINATION_ASSET,
            recipient=os.environ.get("NEAR_INTENTS_RECIPIENT") or None,
            refund_to=os.environ.get("NEAR_INTENTS_REFUND_TO") or None,
            min_amount_usd=float(os.environ.get("NEAR_INTENTS_MIN_AMOUNT_USD", "0.01")),
            max_amount_usd=float(os.environ.get("NEAR_INTENTS_MAX_AMOUNT_USD", "10.0")),
            request_timeout_seconds=float(os.environ.get("NEAR_INTENTS_TIMEOUT_SECONDS", "15")),
            max_retries=int(os.environ.get("NEAR_INTENTS_MAX_RETRIES", "2")),
            rate_limit_seconds=float(os.environ.get("NEAR_INTENTS_RATE_LIMIT_SECONDS", "0.25")),
            market_contract=os.environ.get("NOTCH_MAINNET_MARKET_CONTRACT") or None,
            collateral_token=os.environ.get("NOTCH_MAINNET_COLLATERAL_TOKEN") or None,
        )


class OfficialOneClickClient(TidepoolClient):
    """Official Mainnet API client; inherited methods are read-only here."""

    def __init__(self, config: OfficialMainnetConfig, *, transport=None) -> None:
        super().__init__(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.max_retries,
            rate_limiter=RateLimiter(interval_seconds=config.rate_limit_seconds),
            transport=transport,
            user_agent="NotchOfficial1Click/1 (Mainnet dry quotes only)",
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def submit_deposit(self, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError(
            "OFFICIAL_MAINNET_WET_DISABLED",
            "official Mainnet integration is read-only; deposit submission is disabled",
        )

    def get_status(self, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError(
            "OFFICIAL_MAINNET_STATUS_DISABLED",
            "official Mainnet status tracking is disabled until production execution is approved",
        )


@dataclass(frozen=True)
class OfficialPreparedQuote:
    quote: FundingQuote
    response: QuoteResponse
    validation: QuoteValidation

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote": self.quote.to_dict(),
            "provider_quote": self.response.to_dict(),
            "validation": self.validation.to_dict(),
            "instructions": None,
        }


class OfficialMainnetFundingService:
    """Stateless discovery and dry-quote service for official Mainnet 1Click."""

    def __init__(
        self,
        *,
        config: OfficialMainnetConfig | None,
        client: OfficialOneClickClient | None = None,
        config_error: str | None = None,
        now_fn=now_utc,
    ) -> None:
        self.config = config
        self.client = client or (OfficialOneClickClient(config) if config else None)
        self.config_error = config_error
        self.now_fn = now_fn

    @classmethod
    def from_env(cls) -> "OfficialMainnetFundingService":
        try:
            config = OfficialMainnetConfig.from_env()
        except (TypeError, ValueError) as exc:
            return cls(config=None, config_error=str(exc))
        return cls(config=config)

    @property
    def auth_mode(self) -> str:
        if self.config and self.config.api_key:
            return "partner_jwt_server_side"
        return "unauthenticated_public_api"

    @property
    def auth_configured(self) -> bool:
        return bool(self.config and self.config.api_key)

    def discover_tokens(self) -> list[Token]:
        if self.config_error:
            raise ValidationError("OFFICIAL_PROVIDER_CONFIG_INVALID", self.config_error)
        if self.client is None:
            raise ValidationError("OFFICIAL_PROVIDER_UNAVAILABLE", "official Mainnet provider is not configured")
        return self.client.get_tokens()

    def _mainnet_tokens(self, tokens: list[Token]) -> list[Token]:
        return [
            token
            for token in tokens
            if _is_mainnet_asset(token.asset_id)
        ]

    def discovery(self) -> dict[str, Any]:
        if self.config_error:
            return self._unavailable_discovery(self.config_error)
        try:
            tokens = self._mainnet_tokens(self.discover_tokens())
        except (ValidationError, TidepoolError) as exc:
            return self._unavailable_discovery(str(exc))
        near_destinations = [token for token in tokens if token.blockchain == "near"]
        source_tokens = [token for token in tokens if token.blockchain != "near"]
        configured_destination = next(
            (token for token in near_destinations if token.asset_id == self.config.destination_asset),
            None,
        )
        reasons: list[str] = []
        if not self.config.api_key:
            reasons.append("No partner JWT configured; dry quotes use the unauthenticated fee schedule.")
        if not self.config.destination_asset:
            reasons.append("No independently verified Mainnet destination asset is configured.")
        elif configured_destination is None:
            reasons.append("Configured Mainnet destination asset is not present in the live /v0/tokens catalog.")
        if not self.config.recipient:
            reasons.append("No Mainnet recipient account is configured.")
        if self.config.recipient and not _is_mainnet_account(self.config.recipient):
            reasons.append("Configured recipient is not a Mainnet account.")
        if not self.config.refund_to:
            reasons.append("No Mainnet source-chain refund address is configured.")
        quote_enabled = configured_destination is not None and self.config.allow_dry_quotes
        return {
            "provider": OFFICIAL_PROVIDER_LABEL,
            "provider_id": OFFICIAL_PROVIDER_ID,
            "network": OFFICIAL_NETWORK,
            "environment": OFFICIAL_ENVIRONMENT,
            "tokens": [token.to_dict() for token in tokens],
            "source_tokens": [token.to_dict() for token in source_tokens],
            "destination_candidates": [token.to_dict() for token in near_destinations],
            "routes": self._routes(source_tokens, configured_destination),
            "source_chains": sorted({token.blockchain for token in source_tokens}),
            "destination_asset": configured_destination.asset_id if configured_destination else None,
            "recipient": self.config.recipient if _is_mainnet_account(self.config.recipient) else None,
            "quote_enabled": quote_enabled,
            "quote_mode": "dry_only" if quote_enabled else "unavailable",
            "auth_mode": self.auth_mode,
            "auth_configured": self.auth_configured,
            "credentials_exposed": False,
            "fee_notice": OFFICIAL_FEE_NOTICE,
            "execution_supported": False,
            "execution_reasons": list(MAINNET_EXECUTION_BLOCKERS),
            "unavailable_reasons": reasons,
            "signature_public_key_id": "official-oneclick-manager-ed25519",
            "observed_at": max(
                (token.price_updated_at for token in tokens if token.price_updated_at),
                default=None,
            ),
        }

    def _unavailable_discovery(self, reason: str) -> dict[str, Any]:
        return {
            "provider": OFFICIAL_PROVIDER_LABEL,
            "provider_id": OFFICIAL_PROVIDER_ID,
            "network": OFFICIAL_NETWORK,
            "environment": OFFICIAL_ENVIRONMENT,
            "tokens": [],
            "source_tokens": [],
            "destination_candidates": [],
            "routes": [],
            "source_chains": [],
            "destination_asset": None,
            "recipient": None,
            "quote_enabled": False,
            "quote_mode": "unavailable",
            "auth_mode": self.auth_mode,
            "auth_configured": self.auth_configured,
            "credentials_exposed": False,
            "fee_notice": OFFICIAL_FEE_NOTICE,
            "execution_supported": False,
            "execution_reasons": list(MAINNET_EXECUTION_BLOCKERS),
            "unavailable_reasons": [reason],
            "signature_public_key_id": "official-oneclick-manager-ed25519",
            "observed_at": None,
        }

    @staticmethod
    def _routes(source_tokens: list[Token], destination: Token | None) -> list[dict[str, Any]]:
        if destination is None:
            return []
        return [Route(source=source, destination=destination).to_dict() for source in source_tokens]

    def dry_quote(
        self,
        *,
        source_asset: str,
        amount: str,
        recipient: str | None = None,
        refund_to: str | None = None,
        source_chain: str | None = None,
        destination_asset: str | None = None,
        slippage_bps: int | None = None,
        deadline_minutes: int | None = None,
    ) -> OfficialPreparedQuote:
        if self.config_error:
            raise ValidationError("OFFICIAL_PROVIDER_CONFIG_INVALID", self.config_error)
        if self.config is None or self.client is None:
            raise ValidationError("OFFICIAL_PROVIDER_UNAVAILABLE", "official Mainnet provider is not configured")
        if not self.config.allow_dry_quotes:
            raise ValidationError("OFFICIAL_DRY_QUOTES_DISABLED", "official Mainnet dry quotes are disabled")
        tokens = self.discover_tokens()
        destination = destination_asset or self.config.destination_asset
        target_recipient = recipient or self.config.recipient
        target_refund = refund_to or self.config.refund_to
        if not destination:
            raise ValidationError("MAINNET_DESTINATION_NOT_CONFIGURED", "configure a verified Mainnet destination asset")
        if not target_recipient or not _is_mainnet_account(target_recipient):
            raise ValidationError("MAINNET_RECIPIENT_REQUIRED", "a verified Mainnet recipient account is required")
        if not target_refund:
            raise ValidationError("MAINNET_REFUND_REQUIRED", "a Mainnet source-chain refund address is required")
        now = self.now_fn()
        ttl = int(deadline_minutes or self.config.quote_ttl_seconds)
        ttl = max(60, min(ttl, self.config.max_quote_ttl_seconds))
        request = QuoteRequest(
            dry=True,
            swap_type=SwapType.EXACT_INPUT.value,
            slippage_tolerance=int(slippage_bps or self.config.default_slippage_bps),
            origin_asset=source_asset,
            deposit_type=DepositType.ORIGIN_CHAIN.value,
            destination_asset=destination,
            amount=str(amount),
            refund_to=target_refund,
            refund_type=RefundType.ORIGIN_CHAIN.value,
            recipient=target_recipient,
            recipient_type=RecipientType.DESTINATION_CHAIN.value,
            deadline=iso_utc(now + timedelta(seconds=ttl)) or "",
            deposit_mode=DepositMode.SIMPLE.value,
        )
        route = validate_request(
            request,
            tokens,
            self.config,
            now=now,
            source_chain=source_chain,
            destination_asset=destination,
            require_testnet=False,
        )
        response = self.client.quote(request)
        validation = validate_quote_response(
            response,
            request,
            route,
            self.config,
            now=self.now_fn(),
            verify_signature=self.config.verify_quote_signatures,
            signature_public_key=OFFICIAL_ONE_CLICK_MANAGER_PUBLIC_KEY,
            require_testnet=False,
        )
        quote = FundingQuote(
            quote_id=response.correlation_id,
            correlation_id=response.correlation_id,
            state=FundingState.QUOTED,
            dry=True,
            source_asset=route.source.asset_id,
            source_symbol=route.source.symbol,
            source_chain=route.source.blockchain,
            source_decimals=route.source.decimals,
            destination_asset=route.destination.asset_id,
            destination_symbol=route.destination.symbol,
            destination_decimals=route.destination.decimals,
            amount_in=response.quote.amount_in,
            amount_out=response.quote.amount_out,
            min_amount_out=response.quote.min_amount_out,
            slippage_bps=response.quote_request.slippage_tolerance,
            recipient=response.quote_request.recipient,
            refund_to=response.quote_request.refund_to,
            deposit_type=response.quote_request.deposit_type,
            refund_type=response.quote_request.refund_type,
            deadline=response.quote.deadline,
            deposit_address=None,
            deposit_memo=None,
            signature=response.signature,
            quote_timestamp=response.timestamp,
            created_at=iso_utc(now) or "",
            updated_at=iso_utc(now) or "",
            expires_at=iso_utc(validation.expires_at),
            signature_verified=validation.signature_verified,
            raw_quote=response.raw,
        )
        return OfficialPreparedQuote(quote=quote, response=response, validation=validation)

    def prepare_swap(self, **kwargs: Any) -> OfficialPreparedQuote:
        raise ValidationError(
            "OFFICIAL_MAINNET_WET_DISABLED",
            "official NEAR Intents Mainnet integration is read-only; wet quotes and deposit instructions are disabled",
        )

    def close(self) -> None:
        return None
