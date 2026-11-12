"""Configuration for the S4 Intents funding adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .models import (
    DEFAULT_BASE_URL,
    DEFAULT_MARKET_CONTRACT,
    DEFAULT_RPC_URL,
    DEFAULT_VERIFIER_ACCOUNT,
    DESTINATION_ASSET,
)


@dataclass(frozen=True)
class IntentsConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    destination_asset: str = DESTINATION_ASSET
    source_chain: str = "near"
    verifier_account: str = DEFAULT_VERIFIER_ACCOUNT
    rpc_url: str = DEFAULT_RPC_URL
    market_contract: str = DEFAULT_MARKET_CONTRACT
    data_dir: str = "var/intents"
    min_amount_base_units: int = 1
    max_amount_base_units: int = 10_000_000
    min_amount_usd: float = 0.01
    max_amount_usd: float = 10.0
    default_slippage_bps: int = 100
    max_slippage_bps: int = 5_000
    quote_ttl_seconds: int = 1_800
    max_quote_ttl_seconds: int = 3_600
    request_timeout_seconds: float = 15.0
    max_retries: int = 2
    rate_limit_seconds: float = 0.25
    max_poll_attempts: int = 20
    poll_interval_seconds: float = 2.0
    min_market_entry_base_units: int = 1_000_000
    storage_deposit_yocto: str = "1250000000000000000000"  # 0.00125 NEAR

    @classmethod
    def from_env(cls) -> "IntentsConfig":
        return cls(
            base_url=os.environ.get("TIDEPOOL_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("TIDEPOOL_API_KEY") or None,
            data_dir=os.environ.get("INTENTS_DATA_DIR", "var/intents"),
            rpc_url=os.environ.get("NEAR_RPC_URL", DEFAULT_RPC_URL),
            market_contract=os.environ.get("MARKET_CONTRACT", DEFAULT_MARKET_CONTRACT),
        )
