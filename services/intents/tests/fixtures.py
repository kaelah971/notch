"""Deterministic provider fixtures for S4 tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


NOW = datetime(2026, 11, 12, 7, 0, 0, tzinfo=timezone.utc)
DEADLINE = "2026-11-12T07:30:00Z"
DEPOSIT_ADDRESS = "f45c1398ea7695e2bd15e50ea2aa9cfc8c560b400222382b7b33c53e3d373ef0"
SIGNATURE = "ed25519:" + "1" * 88


TOKENS: list[dict[str, Any]] = [
    {
        "assetId": "nep141:usdc.tidepool-sandbox.testnet",
        "decimals": 6,
        "blockchain": "near",
        "symbol": "USDC",
        "price": 0.999464,
        "priceUpdatedAt": "2026-11-12T06:58:11Z",
        "contractAddress": "usdc.tidepool-sandbox.testnet",
    },
    {
        "assetId": "nep141:usdt.tidepool-sandbox.testnet",
        "decimals": 6,
        "blockchain": "near",
        "symbol": "USDT",
        "price": 0.999032,
        "priceUpdatedAt": "2026-11-12T06:58:11Z",
        "contractAddress": "usdt.tidepool-sandbox.testnet",
    },
    {
        "assetId": "nep141:wnear.tidepool-sandbox.testnet",
        "decimals": 24,
        "blockchain": "near",
        "symbol": "wNEAR",
        "price": 3.5,
        "priceUpdatedAt": "2026-11-12T06:58:11Z",
        "contractAddress": "wnear.tidepool-sandbox.testnet",
    },
    {
        "assetId": "nep141:eth.tidepool-sandbox.testnet",
        "decimals": 18,
        "blockchain": "near",
        "symbol": "ETH",
        "price": 2046.71,
        "priceUpdatedAt": "2026-11-12T06:58:11Z",
        "contractAddress": "eth.tidepool-sandbox.testnet",
    },
    {
        "assetId": "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet",
        "decimals": 6,
        "blockchain": "base",
        "symbol": "USDC",
        "price": 0.999464,
        "priceUpdatedAt": "2026-11-12T06:58:11Z",
        "contractAddress": "0x38d81431B9f76d9699AF7517040D5221D9dEA252",
    },
]


def quote_request(
    *,
    dry: bool,
    deposit_type: str = "INTENTS",
    amount: str = "1000000",
) -> dict[str, Any]:
    return {
        "dry": dry,
        "swapType": "EXACT_INPUT",
        "slippageTolerance": 100,
        "originAsset": "nep141:usdt.tidepool-sandbox.testnet",
        "depositType": deposit_type,
        "destinationAsset": "nep141:usdc.tidepool-sandbox.testnet",
        "amount": amount,
        "refundTo": "notch-dev.testnet",
        "refundType": "INTENTS" if deposit_type == "INTENTS" else "ORIGIN_CHAIN",
        "recipient": "notch-dev.testnet",
        "recipientType": "DESTINATION_CHAIN",
        "deadline": DEADLINE,
        "depositMode": "SIMPLE",
    }


def quote_payload(
    *,
    dry: bool = True,
    deposit_type: str = "INTENTS",
    amount: str = "1000000",
    amount_out: str = "996968",
    min_amount_out: str = "986998",
) -> dict[str, Any]:
    request = quote_request(dry=dry, deposit_type=deposit_type, amount=amount)
    quote: dict[str, Any] = {
        "amountIn": amount,
        "amountInFormatted": "1",
        "amountInUsd": "0.9990",
        "minAmountIn": amount,
        "amountOut": amount_out,
        "amountOutFormatted": "0.996968",
        "amountOutUsd": "0.9964",
        "minAmountOut": min_amount_out,
        "timeEstimate": 10,
    }
    if not dry:
        quote["depositAddress"] = DEPOSIT_ADDRESS
        quote["deadline"] = DEADLINE
        quote["timeWhenInactive"] = DEADLINE
    return {
        "correlationId": "quote-test-1",
        "timestamp": "2026-11-12T07:00:01Z",
        "quoteRequest": request,
        "quote": quote,
        "signature": SIGNATURE,
    }


def quote_response(*, dry: bool = True, **kwargs: Any) -> dict[str, Any]:
    return deepcopy(quote_payload(dry=dry, **kwargs))


def status_payload(
    status: str,
    *,
    amount_out: str = "996968",
    correlation_id: str = "quote-test-1",
    refunded_amount: str | None = None,
    refund_reason: str | None = None,
    near_tx_hashes: list[str] | None = None,
) -> dict[str, Any]:
    response = quote_payload(dry=False)
    swap: dict[str, Any] = {
        "intentHashes": [],
        "nearTxHashes": list(near_tx_hashes or []),
        "originChainTxHashes": [],
        "destinationChainTxHashes": [],
        "withdrawFee": "0",
    }
    if status == "SUCCESS":
        swap["amountOut"] = amount_out
        swap["amountOutFormatted"] = "0.996968"
        swap["amountOutUsd"] = "0.9964"
    if refunded_amount is not None:
        swap["refundedAmount"] = refunded_amount
    if refund_reason is not None:
        swap["refundReason"] = refund_reason
    return {
        "correlationId": correlation_id,
        "quoteResponse": response,
        "status": status,
        "updatedAt": "2026-11-12T07:01:00Z",
        "swapDetails": swap,
    }
