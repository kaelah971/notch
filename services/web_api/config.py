"""Configuration for the S6 frontend-ready HTTP API."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MARKET_CONTRACT = "market.notch-dev.testnet"
DEFAULT_COLLATERAL = "usdc.tidepool-sandbox.testnet"
DEFAULT_RPC = "https://rpc.testnet.near.org"
DEFAULT_RADAR_DB = "var/trend_radar_live_final/radar.sqlite3"
DEFAULT_ORACLE_DBS = (
    "var/oracle_s2_5_short/oracle.sqlite3",
    "var/oracle_live_final/oracle.sqlite3",
)


@dataclass(frozen=True)
class WebAPIConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    max_body_bytes: int = 65_536
    general_rate_limit_per_minute: int = 120
    quote_rate_limit_per_minute: int = 10
    entry_rate_limit_per_minute: int = 30
    market_contract: str = DEFAULT_MARKET_CONTRACT
    collateral_token: str = DEFAULT_COLLATERAL
    rpc_url: str = DEFAULT_RPC
    radar_db: str = DEFAULT_RADAR_DB
    oracle_db_paths: tuple[str, ...] = DEFAULT_ORACLE_DBS
    network: str = "testnet"
    request_timeout_seconds: float = 15.0
    pulse_db_path: str = "var/web_api/pulse.sqlite3"
    pulse_start_block: int | None = None
    pulse_max_blocks_per_request: int = 25

    @classmethod
    def from_env(cls) -> "WebAPIConfig":
        origins = tuple(
            item.strip()
            for item in os.environ.get(
                "WEB_API_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000,"
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if item.strip()
        )
        oracle_paths = tuple(
            item.strip()
            for item in os.environ.get(
                "ORACLE_DB_PATHS",
                ",".join(DEFAULT_ORACLE_DBS),
            ).split(",")
            if item.strip()
        )
        return cls(
            host=os.environ.get("WEB_API_HOST", "127.0.0.1"),
            port=int(os.environ.get("WEB_API_PORT", "8000")),
            cors_origins=origins,
            max_body_bytes=int(os.environ.get("WEB_API_MAX_BODY_BYTES", "65536")),
            general_rate_limit_per_minute=int(
                os.environ.get("WEB_API_RATE_LIMIT_PER_MINUTE", "120")
            ),
            quote_rate_limit_per_minute=int(
                os.environ.get("WEB_API_QUOTE_RATE_LIMIT_PER_MINUTE", "10")
            ),
            entry_rate_limit_per_minute=int(
                os.environ.get("WEB_API_ENTRY_RATE_LIMIT_PER_MINUTE", "30")
            ),
            market_contract=os.environ.get("MARKET_CONTRACT", DEFAULT_MARKET_CONTRACT),
            collateral_token=os.environ.get("COLLATERAL_TOKEN", DEFAULT_COLLATERAL),
            rpc_url=os.environ.get("NEAR_RPC_URL", DEFAULT_RPC),
            radar_db=os.environ.get("RADAR_DB_PATH", DEFAULT_RADAR_DB),
            oracle_db_paths=oracle_paths,
            network=os.environ.get("NEAR_NETWORK", "testnet"),
            request_timeout_seconds=float(
                os.environ.get("WEB_API_REQUEST_TIMEOUT_SECONDS", "15")
            ),
            pulse_db_path=os.environ.get(
                "PULSE_DB_PATH", "var/web_api/pulse.sqlite3"
            ),
            pulse_start_block=(
                int(os.environ["PULSE_START_BLOCK"])
                if os.environ.get("PULSE_START_BLOCK")
                else None
            ),
            pulse_max_blocks_per_request=max(
                1, int(os.environ.get("PULSE_MAX_BLOCKS_PER_REQUEST", "25"))
            ),
        )
