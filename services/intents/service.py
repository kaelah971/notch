"""Funding orchestration for the S4 Tidepool testnet adapter.

The service prepares quotes and deposit instructions, persists provider
references and advances the local funding state machine.  It never signs or
broadcasts a chain transaction and never submits a market position.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from services.trend_radar.models import iso_utc, now_utc, parse_iso

from .balance import (
    FundingReadiness,
    NearRpcClient,
    read_funding_readiness,
    verify_destination_balance,
)
from .client import TidepoolClient, TidepoolError
from .config import IntentsConfig
from .instructions import build_deposit_instructions
from .models import (
    DepositInstructions,
    DepositMode,
    DepositType,
    FundingQuote,
    FundingState,
    ProviderStatus,
    QuoteRequest,
    QuoteResponse,
    RecipientType,
    RefundType,
    StatusResponse,
    SwapType,
    TERMINAL_STATES,
    Token,
)
from .store import FundingStore
from .validation import (
    QuoteValidation,
    Route,
    ValidationError,
    format_base_units,
    select_route,
    supported_routes,
    validate_quote_response,
    validate_request,
)


@dataclass(frozen=True)
class PreparedQuote:
    quote: FundingQuote
    response: QuoteResponse
    validation: QuoteValidation
    instructions: DepositInstructions | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote": self.quote.to_dict(),
            "provider_quote": self.response.to_dict(),
            "validation": self.validation.to_dict(),
            "instructions": self.instructions.to_dict() if self.instructions else None,
        }


class IntentsFundingService:
    def __init__(
        self,
        *,
        client: TidepoolClient,
        store: FundingStore,
        config: IntentsConfig,
        reader: NearRpcClient,
        now_fn: Callable[[], datetime] = now_utc,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.store = store
        self.config = config
        self.reader = reader
        self.now_fn = now_fn
        self.sleep = sleep

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def discover_tokens(self, *, include_ondo: bool = False) -> list[Token]:
        return self.client.get_tokens(include_ondo=include_ondo)

    def supported_routes(self) -> list[Route]:
        return supported_routes(self.discover_tokens(), self.config)

    def destination_token(self, tokens: list[Token] | None = None) -> Token:
        tokens = tokens or self.discover_tokens()
        for token in tokens:
            if token.asset_id == self.config.destination_asset:
                return token
        raise ValidationError(
            "DESTINATION_ASSET_UNAVAILABLE",
            f"destination asset is not in /v0/tokens: {self.config.destination_asset}",
            field="destinationAsset",
        )

    # ------------------------------------------------------------------
    # Quote preparation
    # ------------------------------------------------------------------
    def build_request(
        self,
        *,
        source_asset: str,
        amount: str,
        recipient: str,
        refund_to: str | None = None,
        dry: bool,
        deposit_type: str = DepositType.INTENTS.value,
        slippage_bps: int | None = None,
        deadline_minutes: int | None = None,
    ) -> tuple[QuoteRequest, Route, list[Token]]:
        now = self.now_fn()
        tokens = self.discover_tokens()
        route = select_route(tokens, source_asset, self.config)
        ttl_seconds = (
            int(deadline_minutes) * 60
            if deadline_minutes is not None
            else self.config.quote_ttl_seconds
        )
        ttl_seconds = max(60, min(ttl_seconds, self.config.max_quote_ttl_seconds))
        request = QuoteRequest(
            dry=bool(dry),
            swap_type=SwapType.EXACT_INPUT.value,
            slippage_tolerance=(
                int(slippage_bps)
                if slippage_bps is not None
                else self.config.default_slippage_bps
            ),
            origin_asset=source_asset,
            deposit_type=deposit_type,
            destination_asset=self.config.destination_asset,
            amount=str(amount),
            refund_to=refund_to or recipient,
            refund_type=(
                RefundType.INTENTS.value
                if deposit_type == DepositType.INTENTS.value
                else RefundType.ORIGIN_CHAIN.value
            ),
            recipient=recipient,
            recipient_type=RecipientType.DESTINATION_CHAIN.value,
            deadline=iso_utc(now + timedelta(seconds=ttl_seconds)) or "",
            deposit_mode=DepositMode.SIMPLE.value,
        )
        validate_request(request, tokens, self.config, now=now)
        return request, route, tokens

    def dry_quote(
        self,
        *,
        source_asset: str,
        amount: str,
        recipient: str,
        refund_to: str | None = None,
        deposit_type: str = DepositType.INTENTS.value,
        slippage_bps: int | None = None,
        deadline_minutes: int | None = None,
    ) -> PreparedQuote:
        request, route, _tokens = self.build_request(
            source_asset=source_asset,
            amount=amount,
            recipient=recipient,
            refund_to=refund_to,
            dry=True,
            deposit_type=deposit_type,
            slippage_bps=slippage_bps,
            deadline_minutes=deadline_minutes,
        )
        response = self.client.quote(request)
        validation = validate_quote_response(
            response,
            request,
            route,
            self.config,
            now=self.now_fn(),
        )
        quote = self._record_quote(response, route, validation, dry=True, instructions=None)
        return PreparedQuote(
            quote=quote,
            response=response,
            validation=validation,
            instructions=None,
        )

    def prepare_swap(
        self,
        *,
        source_asset: str,
        amount: str,
        recipient: str,
        refund_to: str | None = None,
        deposit_type: str = DepositType.INTENTS.value,
        slippage_bps: int | None = None,
        deadline_minutes: int | None = None,
    ) -> PreparedQuote:
        request, route, _tokens = self.build_request(
            source_asset=source_asset,
            amount=amount,
            recipient=recipient,
            refund_to=refund_to,
            dry=False,
            deposit_type=deposit_type,
            slippage_bps=slippage_bps,
            deadline_minutes=deadline_minutes,
        )
        response = self.client.quote(request)
        validation = validate_quote_response(
            response,
            request,
            route,
            self.config,
            now=self.now_fn(),
        )
        instructions = build_deposit_instructions(
            response,
            route.source,
            route.destination,
            self.config,
            now=self.now_fn(),
        )
        quote = self._record_quote(
            response,
            route,
            validation,
            dry=False,
            instructions=instructions,
        )
        return PreparedQuote(
            quote=quote,
            response=response,
            validation=validation,
            instructions=instructions,
        )

    def _record_quote(
        self,
        response: QuoteResponse,
        route: Route,
        validation: QuoteValidation,
        *,
        dry: bool,
        instructions: DepositInstructions | None,
    ) -> FundingQuote:
        existing = self.store.get_quote(response.correlation_id)
        if existing is not None:
            return existing
        now = self.now_fn()
        destination_contract = (
            route.destination.contract_address
            or route.destination.asset_id.removeprefix("nep141:")
        )
        balance_before: str | None = None
        balance_error: str | None = None
        try:
            balance_before = str(
                self.reader.ft_balance_of(destination_contract, response.quote_request.recipient)
            )
        except Exception as exc:
            balance_error = f"could not record pre-swap USDC balance: {type(exc).__name__}"
        quote = FundingQuote(
            quote_id=response.correlation_id,
            correlation_id=response.correlation_id,
            state=FundingState.QUOTED if dry else FundingState.AWAITING_DEPOSIT,
            dry=dry,
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
            deadline=response.quote.deadline or response.quote_request.deadline,
            deposit_address=response.quote.deposit_address,
            deposit_memo=response.quote.deposit_memo,
            signature=response.signature,
            quote_timestamp=response.timestamp,
            created_at=iso_utc(now) or "",
            updated_at=iso_utc(now) or "",
            balance_before=balance_before,
            last_error=balance_error,
            expires_at=iso_utc(validation.expires_at),
            raw_quote=response.raw,
        )
        self.store.save_quote(quote)
        self.store.append_event(
            quote.quote_id,
            "quote_prepared",
            {
                "dry": dry,
                "state": quote.state.value,
                "source_asset": quote.source_asset,
                "amount_in": quote.amount_in,
                "amount_out": quote.amount_out,
                "min_amount_out": quote.min_amount_out,
                "expires_at": quote.expires_at,
                "balance_before": balance_before,
                "balance_error": balance_error,
                "instructions_supported": instructions.supported if instructions else None,
            },
            created_at=quote.created_at,
        )
        return quote

    # ------------------------------------------------------------------
    # Deposit tracking
    # ------------------------------------------------------------------
    def deposit_instructions(self, quote_id: str) -> DepositInstructions:
        quote = self.store.require_quote(quote_id)
        if quote.dry:
            raise ValidationError("DRY_QUOTE", "dry quotes have no deposit instructions")
        if quote.state in TERMINAL_STATES:
            raise ValidationError(
                "QUOTE_TERMINAL",
                f"quote is already {quote.state.value}; request a new quote",
            )
        now = self.now_fn()
        expires = parse_iso(quote.expires_at)
        if expires is not None and expires <= now:
            quote.state = FundingState.EXPIRED
            quote.updated_at = iso_utc(now) or ""
            self.store.save_quote(quote)
            raise ValidationError("QUOTE_EXPIRED", "quote has expired; request a new quote")
        response = QuoteResponse.from_provider(quote.raw_quote)
        tokens = self.discover_tokens()
        source = next((t for t in tokens if t.asset_id == quote.source_asset), None)
        destination = next((t for t in tokens if t.asset_id == quote.destination_asset), None)
        if source is None or destination is None:
            raise ValidationError(
                "TOKEN_METADATA_MISSING",
                "live token metadata no longer contains the quote assets",
            )
        return build_deposit_instructions(
            response,
            source,
            destination,
            self.config,
            now=now,
        )

    def record_deposit(
        self,
        quote_id: str,
        tx_hash: str,
        *,
        submit: bool = False,
    ) -> FundingQuote:
        quote = self.store.require_quote(quote_id)
        if quote.dry:
            raise ValidationError("DRY_QUOTE", "dry quotes cannot receive deposits")
        if quote.state in TERMINAL_STATES:
            raise ValidationError(
                "QUOTE_TERMINAL",
                f"quote is already {quote.state.value}; refusing deposit",
            )
        now = self.now_fn()
        expires = parse_iso(quote.expires_at)
        if expires is not None and expires <= now and not quote.deposit_tx_hash:
            quote.state = FundingState.EXPIRED
            quote.updated_at = iso_utc(now) or ""
            self.store.save_quote(quote)
            raise ValidationError("QUOTE_EXPIRED", "quote has expired; refusing deposit")
        quote = self.store.record_deposit(
            quote_id,
            tx_hash,
            recorded_at=iso_utc(now) or "",
            submitted=False,
        )
        if submit:
            try:
                status = self.client.submit_deposit(
                    tx_hash=tx_hash,
                    deposit_address=quote.deposit_address or "",
                    near_sender_account=quote.recipient,
                    memo=quote.deposit_memo,
                )
                quote = self._apply_status(quote, status, now=self.now_fn())
                self.store.record_deposit(
                    quote_id,
                    tx_hash,
                    recorded_at=iso_utc(self.now_fn()) or "",
                    submitted=True,
                )
            except TidepoolError as exc:
                quote = self.store.require_quote(quote_id)
                quote.last_error = str(exc)
                quote.updated_at = iso_utc(self.now_fn()) or ""
                self.store.save_quote(quote)
                self.store.append_event(
                    quote_id,
                    "deposit_submit_failed",
                    exc.as_dict(),
                    created_at=quote.updated_at,
                )
        return self.store.require_quote(quote_id)

    # ------------------------------------------------------------------
    # Status and balance verification
    # ------------------------------------------------------------------
    def refresh_status(
        self,
        quote_id: str,
        *,
        max_attempts: int | None = None,
        interval_seconds: float | None = None,
    ) -> FundingQuote:
        quote = self.store.require_quote(quote_id)
        if quote.dry:
            raise ValidationError("DRY_QUOTE", "dry quotes have no provider status")
        if not quote.deposit_address:
            raise ValidationError("MISSING_DEPOSIT_ADDRESS", "quote has no deposit address")
        if quote.state in TERMINAL_STATES:
            return quote
        attempts = max(1, int(max_attempts if max_attempts is not None else self.config.max_poll_attempts))
        interval = max(
            0.0,
            float(
                interval_seconds
                if interval_seconds is not None
                else self.config.poll_interval_seconds
            ),
        )
        for attempt in range(attempts):
            try:
                status = self.client.get_status(
                    deposit_address=quote.deposit_address,
                    memo=quote.deposit_memo,
                )
                quote = self._apply_status(quote, status, now=self.now_fn())
            except TidepoolError as exc:
                quote = self.store.require_quote(quote_id)
                quote.last_error = str(exc)
                quote.updated_at = iso_utc(self.now_fn()) or ""
                self.store.save_quote(quote)
                self.store.append_event(
                    quote_id,
                    "status_poll_failed",
                    exc.as_dict(),
                    created_at=quote.updated_at,
                )
                if not exc.retryable:
                    break
            quote = self.store.require_quote(quote_id)
            if quote.state in TERMINAL_STATES:
                break
            if attempt < attempts - 1:
                self.sleep(interval)
        return self.store.require_quote(quote_id)

    def _apply_status(
        self,
        quote: FundingQuote,
        status: StatusResponse,
        *,
        now: datetime,
    ) -> FundingQuote:
        if quote.state in TERMINAL_STATES:
            return quote
        quote.poll_count += 1
        quote.provider_status = status.status
        quote.raw_status = status.raw
        quote.updated_at = iso_utc(now) or ""
        provider = status.status
        swap = status.swap_details
        if swap.refund_reason:
            quote.refund_reason = swap.refund_reason
        if swap.refunded_amount:
            quote.refunded_amount = swap.refunded_amount
        if swap.near_tx_hashes:
            quote.refund_tx_hash = swap.near_tx_hashes[-1] if provider == ProviderStatus.REFUNDED.value else quote.refund_tx_hash

        if provider == ProviderStatus.PENDING_DEPOSIT.value:
            expires = parse_iso(quote.expires_at)
            if expires is not None and expires <= now and not quote.deposit_tx_hash:
                quote.state = FundingState.EXPIRED
            elif quote.state in {FundingState.QUOTED, FundingState.AWAITING_DEPOSIT}:
                quote.state = FundingState.AWAITING_DEPOSIT
        elif provider in {
            ProviderStatus.KNOWN_DEPOSIT_TX.value,
            ProviderStatus.INCOMPLETE_DEPOSIT.value,
        }:
            quote.state = FundingState.DEPOSIT_DETECTED
        elif provider == ProviderStatus.PROCESSING.value:
            quote.state = FundingState.PROCESSING
        elif provider == ProviderStatus.REFUNDED.value:
            quote.state = FundingState.REFUNDED
        elif provider == ProviderStatus.FAILED.value:
            quote.state = FundingState.FAILED
            quote.last_error = swap.refund_reason or "provider reported FAILED"
        elif provider == ProviderStatus.SUCCESS.value:
            token = self._token_for_quote(quote)
            check = verify_destination_balance(
                self.reader,
                quote,
                token,
                now=now,
            )
            quote.balance_after = check.after
            quote.balance_delta = check.delta
            quote.balance_verified = check.verified
            if check.verified:
                quote.state = FundingState.SUCCESS
                quote.last_error = None
            else:
                quote.state = FundingState.PROCESSING
                quote.last_error = check.error
        else:
            quote.state = FundingState.PROCESSING
            quote.last_error = f"unknown provider status: {provider}"
        self.store.save_quote(quote)
        self.store.append_event(
            quote.quote_id,
            "provider_status",
            {
                "provider_status": provider,
                "state": quote.state.value,
                "balance_verified": quote.balance_verified,
                "balance_delta": quote.balance_delta,
                "refund_reason": quote.refund_reason,
                "refunded_amount": quote.refunded_amount,
                "last_error": quote.last_error,
            },
            created_at=quote.updated_at,
        )
        return quote

    def verify_balance(self, quote_id: str) -> FundingQuote:
        quote = self.store.require_quote(quote_id)
        if quote.dry:
            raise ValidationError("DRY_QUOTE", "dry quotes have no balance to verify")
        token = self._token_for_quote(quote)
        check = verify_destination_balance(
            self.reader,
            quote,
            token,
            now=self.now_fn(),
        )
        quote.balance_after = check.after
        quote.balance_delta = check.delta
        quote.balance_verified = check.verified
        quote.updated_at = iso_utc(self.now_fn()) or ""
        if check.verified and quote.provider_status == ProviderStatus.SUCCESS.value:
            quote.state = FundingState.SUCCESS
            quote.last_error = None
        elif not check.verified:
            quote.last_error = check.error
        self.store.save_quote(quote)
        self.store.append_event(
            quote_id,
            "balance_verification",
            check.to_dict(),
            created_at=quote.updated_at,
        )
        return quote

    def _token_for_quote(self, quote: FundingQuote) -> Token:
        tokens = self.discover_tokens()
        for token in tokens:
            if token.asset_id == quote.destination_asset:
                return token
        raise ValidationError(
            "DESTINATION_ASSET_UNAVAILABLE",
            f"destination asset missing from /v0/tokens: {quote.destination_asset}",
        )

    # ------------------------------------------------------------------
    # Notch readiness
    # ------------------------------------------------------------------
    def funding_readiness(self, account: str) -> FundingReadiness:
        token = self.destination_token()
        return read_funding_readiness(
            self.reader,
            account=account,
            token=token,
            min_market_entry=self.config.min_market_entry_base_units,
            now=self.now_fn(),
        )

    def get_available_collateral(self, account: str) -> dict[str, Any]:
        return self.funding_readiness(account).to_dict()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    def get_quote(self, quote_id: str) -> FundingQuote:
        return self.store.require_quote(quote_id)

    def list_quotes(self, *, limit: int = 50) -> list[FundingQuote]:
        return self.store.list_quotes(limit=limit)

    def quote_summary(self, quote: FundingQuote) -> dict[str, Any]:
        return {
            **quote.to_dict(),
            "amount_in_display": format_base_units(quote.amount_in, quote.source_decimals),
            "amount_out_display": format_base_units(quote.amount_out, quote.destination_decimals),
            "min_amount_out_display": format_base_units(
                quote.min_amount_out, quote.destination_decimals
            ),
            "events": self.store.list_events(quote.quote_id),
        }
