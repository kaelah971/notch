"""Read-only NEAR testnet market and token access for S6."""

from __future__ import annotations

from typing import Any

from services.intents.balance import NearRpcClient
from services.intents.config import IntentsConfig


class ChainReadError(RuntimeError):
    pass


class MarketChainReader:
    def __init__(self, *, config: IntentsConfig, reader: NearRpcClient | None = None) -> None:
        self.config = config
        self.reader = reader or NearRpcClient(
            rpc_url=config.rpc_url,
            timeout_seconds=config.request_timeout_seconds,
        )

    def now_ns(self) -> int:
        return self.reader.latest_block_timestamp_ns()

    def get_contract_config(self) -> dict[str, Any]:
        value = self.reader.view(self.config.market_contract, "get_contract_config", {})
        if not isinstance(value, dict):
            raise ChainReadError("invalid contract config response")
        return value

    def get_market_count(self) -> int:
        value = self.reader.view(self.config.market_contract, "get_market_count", {})
        return int(value or 0)

    def list_markets(self) -> list[dict[str, Any]]:
        count = self.get_market_count()
        markets: list[dict[str, Any]] = []
        from_index = 0
        while from_index < count:
            page = self.reader.view(
                self.config.market_contract,
                "list_markets",
                {"from_index": from_index, "limit": 50},
            )
            if not isinstance(page, list):
                raise ChainReadError("invalid list_markets response")
            markets.extend(item for item in page if isinstance(item, dict))
            from_index += 50
        return markets

    def get_market(self, market_id: str) -> dict[str, Any] | None:
        value = self.reader.view(
            self.config.market_contract, "get_market", {"market_id": market_id}
        )
        return value if isinstance(value, dict) else None

    def get_market_totals(self, market_id: str) -> dict[str, Any] | None:
        value = self.reader.view(
            self.config.market_contract, "get_market_totals", {"market_id": market_id}
        )
        return value if isinstance(value, dict) else None

    def get_position(self, market_id: str, account_id: str) -> dict[str, Any] | None:
        value = self.reader.view(
            self.config.market_contract,
            "get_position",
            {"market_id": market_id, "account_id": account_id},
        )
        return value if isinstance(value, dict) else None

    def ft_metadata(self, contract: str) -> dict[str, Any]:
        value = self.reader.view(contract, "ft_metadata", {})
        if not isinstance(value, dict):
            raise ChainReadError(f"invalid ft_metadata response for {contract}")
        return value

    def ft_balance(self, contract: str, account_id: str) -> str:
        value = self.reader.view(contract, "ft_balance_of", {"account_id": account_id})
        try:
            return str(int(value))
        except (TypeError, ValueError) as exc:
            raise ChainReadError(f"invalid ft_balance_of response for {contract}") from exc

    def storage_balance(self, contract: str, account_id: str) -> dict[str, Any] | None:
        value = self.reader.view(
            contract, "storage_balance_of", {"account_id": account_id}
        )
        return value if isinstance(value, dict) else None

    def native_balance(self, account_id: str) -> str:
        value = self.reader.view_account(account_id)
        return str(value.get("amount", "0"))
