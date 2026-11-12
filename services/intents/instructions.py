"""Accurate NEAR-testnet deposit instructions for a Tidepool quote.

The provider's quote is the only source of the deposit address.  This module
never derives or guesses an address, and it never signs or broadcasts.
"""

from __future__ import annotations

from datetime import datetime

from services.trend_radar.models import parse_iso

from .config import IntentsConfig
from .models import (
    DepositInstructions,
    DepositStep,
    DepositType,
    QuoteResponse,
    Token,
)
from .validation import ValidationError


def build_deposit_instructions(
    response: QuoteResponse,
    source: Token,
    destination: Token,
    config: IntentsConfig,
    *,
    now: datetime,
) -> DepositInstructions:
    request = response.quote_request
    quote = response.quote
    deposit_address = quote.deposit_address
    if request.dry:
        raise ValidationError(
            "DRY_QUOTE",
            "dry quotes have no deposit instructions; request a live quote",
            field="dry",
        )
    if not deposit_address:
        raise ValidationError(
            "MISSING_DEPOSIT_ADDRESS",
            "live quote has no deposit address",
            field="depositAddress",
        )
    deadline = parse_iso(quote.deadline) or parse_iso(request.deadline)
    if deadline is None:
        raise ValidationError("INVALID_DEADLINE", "quote has no deadline", field="deadline")
    if deadline <= now:
        raise ValidationError(
            "QUOTE_EXPIRED",
            "quote deadline has passed; request a new quote",
            field="deadline",
        )

    warnings = [
        "TESTNET ONLY: Tidepool test tokens have no value. Never send real assets.",
        "Use the exact provider deposit address and memo; do not substitute another address.",
        "The backend does not sign or broadcast these steps. User approval is required.",
    ]
    if quote.deposit_memo:
        warnings.append("Preserve the provider deposit memo exactly.")
    if request.deposit_mode == "MEMO" and not quote.deposit_memo:
        raise ValidationError(
            "MISSING_DEPOSIT_MEMO",
            "provider quote requires a memo but none was returned",
            field="depositMemo",
        )

    if source.blockchain != "near":
        return DepositInstructions(
            quote_id=response.correlation_id,
            source_chain=source.blockchain,
            source_asset=source.asset_id,
            source_symbol=source.symbol,
            source_decimals=source.decimals,
            destination_asset=destination.asset_id,
            destination_symbol=destination.symbol,
            destination_decimals=destination.decimals,
            amount_in=quote.amount_in,
            min_amount_out=quote.min_amount_out,
            deposit_type=request.deposit_type,
            provider_deposit_address=deposit_address,
            deposit_memo=quote.deposit_memo,
            recipient=request.recipient,
            refund_to=request.refund_to,
            deadline=quote.deadline or request.deadline,
            steps=[],
            warnings=warnings,
            supported=False,
            blocker=f"deposit instructions for source chain {source.blockchain} are not implemented yet",
        )

    steps: list[DepositStep] = []
    if request.deposit_type == DepositType.INTENTS.value:
        args: dict[str, object] = {
            "receiver_id": config.verifier_account,
            "amount": quote.amount_in,
            "msg": deposit_address,
        }
        if quote.deposit_memo:
            args["memo"] = quote.deposit_memo
        steps.append(
            DepositStep(
                step=1,
                action="ft_transfer_call_to_intents_verifier",
                contract=source.contract_address or source.asset_id.removeprefix("nep141:"),
                method="ft_transfer_call",
                args=args,
                gas_tgas=100,
                attached_deposit_yocto="1",
                note=(
                    "Deposit into the Intents verifier. The msg is the quote deposit "
                    "address; no separate storage registration is required."
                ),
            )
        )
    elif request.deposit_type == DepositType.ORIGIN_CHAIN.value:
        token_contract = source.contract_address or source.asset_id.removeprefix("nep141:")
        steps.append(
            DepositStep(
                step=1,
                action="storage_deposit_for_deposit_account",
                contract=token_contract,
                method="storage_deposit",
                args={"account_id": deposit_address, "registration_only": True},
                gas_tgas=30,
                attached_deposit_yocto=config.storage_deposit_yocto,
                note=(
                    "Register the quote's fresh NEAR deposit account on the source "
                    "token contract. Verify the current storage price before sending."
                ),
            )
        )
        transfer_args: dict[str, object] = {
            "receiver_id": deposit_address,
            "amount": quote.amount_in,
        }
        if quote.deposit_memo:
            transfer_args["memo"] = quote.deposit_memo
        steps.append(
            DepositStep(
                step=2,
                action="ft_transfer_to_origin_chain_deposit_account",
                contract=token_contract,
                method="ft_transfer",
                args=transfer_args,
                gas_tgas=30,
                attached_deposit_yocto="1",
                note=(
                    "Send exactly quote.amountIn to the provider deposit account. "
                    "Do not add funds beyond the quoted amount."
                ),
            )
        )
    else:
        raise ValidationError(
            "UNSUPPORTED_DEPOSIT_TYPE",
            f"unsupported deposit type: {request.deposit_type}",
            field="depositType",
        )

    return DepositInstructions(
        quote_id=response.correlation_id,
        source_chain=source.blockchain,
        source_asset=source.asset_id,
        source_symbol=source.symbol,
        source_decimals=source.decimals,
        destination_asset=destination.asset_id,
        destination_symbol=destination.symbol,
        destination_decimals=destination.decimals,
        amount_in=quote.amount_in,
        min_amount_out=quote.min_amount_out,
        deposit_type=request.deposit_type,
        provider_deposit_address=deposit_address,
        deposit_memo=quote.deposit_memo,
        recipient=request.recipient,
        refund_to=request.refund_to,
        deadline=quote.deadline or request.deadline,
        steps=steps,
        warnings=warnings,
        supported=True,
    )
