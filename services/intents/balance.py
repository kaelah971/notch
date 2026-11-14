"""NEAR RPC reads for destination-collateral verification (S4).

This module only reads chain state.  It never signs or sends a transaction.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from services.trend_radar.models import iso_utc

from .config import IntentsConfig
from .models import BalanceCheck, FinalizedBalanceRead, FundingQuote, Token
from .validation import parse_base_units


class NearRpcError(RuntimeError):
    pass


@dataclass(frozen=True)
class FundingReadiness:
    account: str
    asset_id: str
    symbol: str
    decimals: int
    balance: str
    storage_registered: bool
    storage_total: str | None
    min_market_entry: str
    ready: bool
    checked_at: str
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "asset_id": self.asset_id,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "balance": self.balance,
            "storage_registered": self.storage_registered,
            "storage_total": self.storage_total,
            "min_market_entry": self.min_market_entry,
            "ready": self.ready,
            "checked_at": self.checked_at,
            "blocker": self.blocker,
        }


class NearRpcClient:
    def __init__(
        self,
        *,
        rpc_url: str,
        timeout_seconds: float = 15.0,
        transport: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._default_transport

    def _default_transport(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise NearRpcError(f"NEAR RPC error: {type(exc).__name__}") from exc
        if "error" in data:
            raise NearRpcError(json.dumps(data["error"])[:500])
        return data.get("result") or {}

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        return self.transport(
            {"jsonrpc": "2.0", "id": "notch-s4", "method": method, "params": params},
            self.timeout_seconds,
        )

    def _view_result(
        self, account_id: str, method_name: str, args: dict[str, Any] | None = None
    ) -> tuple[Any, dict[str, Any]]:
        result = self._rpc(
            "query",
            {
                "request_type": "call_function",
                "finality": "final",
                "account_id": account_id,
                "method_name": method_name,
                "args_base64": base64.b64encode(
                    json.dumps(args or {}, separators=(",", ":")).encode("utf-8")
                ).decode("ascii"),
            },
        )
        raw = bytes(result.get("result", []))
        if not raw:
            return None, result
        return json.loads(raw.decode("utf-8")), result

    def view(self, account_id: str, method_name: str, args: dict[str, Any] | None = None) -> Any:
        value, _result = self._view_result(account_id, method_name, args)
        return value

    def view_finalized(
        self, account_id: str, method_name: str, args: dict[str, Any] | None = None
    ) -> tuple[Any, int, str]:
        value, result = self._view_result(account_id, method_name, args)
        block_height = result.get("block_height")
        block_hash = result.get("block_hash")
        if not isinstance(block_height, int) or block_height <= 0 or not isinstance(block_hash, str) or not block_hash:
            raise NearRpcError("finalized NEAR view did not include block provenance")
        return value, block_height, block_hash

    def view_account(self, account_id: str) -> dict[str, Any]:
        return self._rpc(
            "query",
            {"request_type": "view_account", "finality": "final", "account_id": account_id},
        )

    def view_access_key(self, account_id: str, public_key: str) -> dict[str, Any]:
        return self._rpc(
            "query",
            {
                "request_type": "view_access_key",
                "finality": "final",
                "account_id": account_id,
                "public_key": public_key,
            },
        )

    def transaction_status(self, tx_hash: str, signer_id: str) -> dict[str, Any]:
        return self._rpc("EXPERIMENTAL_tx_status", [tx_hash, signer_id])

    def block_by_id(self, block_id: str) -> dict[str, Any]:
        return self._rpc("block", {"block_id": block_id})

    def latest_block_timestamp_ns(self) -> int:
        result = self._rpc("block", {"finality": "final"})
        return int(result["header"]["timestamp"])

    def ft_balance_of(self, token_contract: str, account_id: str) -> int:
        value = self.view(token_contract, "ft_balance_of", {"account_id": account_id})
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise NearRpcError(f"invalid ft_balance_of response for {token_contract}") from exc

    def ft_balance_finalized(self, token_contract: str, account_id: str) -> FinalizedBalanceRead:
        value, block_height, block_hash = self.view_finalized(
            token_contract,
            "ft_balance_of",
            {"account_id": account_id},
        )
        try:
            balance = int(value)
        except (TypeError, ValueError) as exc:
            raise NearRpcError(f"invalid ft_balance_of response for {token_contract}") from exc
        if balance < 0:
            raise NearRpcError("negative finalized token balance")
        return FinalizedBalanceRead(
            balance=balance,
            block_height=block_height,
            block_hash=block_hash,
            finality="final",
            rpc_source=self.rpc_url,
        )

    def storage_balance_of(self, token_contract: str, account_id: str) -> dict[str, Any] | None:
        value = self.view(token_contract, "storage_balance_of", {"account_id": account_id})
        if value is None:
            return None
        if not isinstance(value, dict):
            raise NearRpcError("invalid storage_balance_of response")
        return value


def read_funding_readiness(
    reader: NearRpcClient,
    *,
    account: str,
    token: Token,
    min_market_entry: int,
    now: datetime,
) -> FundingReadiness:
    contract = token.contract_address or token.asset_id.removeprefix("nep141:")
    balance = reader.ft_balance_of(contract, account)
    storage = reader.storage_balance_of(contract, account)
    registered = storage is not None
    blocker = None
    if not registered:
        blocker = "USDC storage is not registered on the wallet"
    elif balance < min_market_entry:
        blocker = (
            f"balance {balance} is below the market minimum {min_market_entry} base units"
        )
    return FundingReadiness(
        account=account,
        asset_id=token.asset_id,
        symbol=token.symbol,
        decimals=token.decimals,
        balance=str(balance),
        storage_registered=registered,
        storage_total=(storage or {}).get("total"),
        min_market_entry=str(min_market_entry),
        ready=registered and balance >= min_market_entry,
        checked_at=iso_utc(now) or "",
        blocker=blocker,
    )


def verify_destination_balance(
    reader: NearRpcClient,
    quote: FundingQuote,
    token: Token,
    *,
    now: datetime,
    before_override: str | None = None,
    baseline_observation_id: str | None = None,
    baseline_error: str | None = None,
) -> BalanceCheck:
    contract = token.contract_address or token.asset_id.removeprefix("nep141:")
    raw_before = before_override if before_override is not None else quote.balance_before
    if raw_before is None:
        return BalanceCheck(
            account=quote.recipient,
            asset_id=token.asset_id,
            before="",
            after="",
            delta="",
            required=quote.min_amount_out,
            verified=False,
            checked_at=iso_utc(now) or "",
            error=baseline_error or "balance_before was not recorded; cannot verify the destination increase",
            baseline_observation_id=baseline_observation_id,
        )
    try:
        before = int(raw_before)
        if before < 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise NearRpcError("invalid balance_before") from exc

    finalized_reader = getattr(reader, "ft_balance_finalized", None)
    after_read: FinalizedBalanceRead | None = None
    if callable(finalized_reader):
        after_read = finalized_reader(contract, quote.recipient)
        after = after_read.balance
    else:
        after = reader.ft_balance_of(contract, quote.recipient)

    required = parse_base_units(quote.min_amount_out, field="minAmountOut")
    delta = after - before
    verified = delta >= required and delta > 0
    error = None
    if not verified:
        error = (
            f"destination balance delta {delta} is below required {required}; "
            "provider SUCCESS alone is not sufficient"
        )
    return BalanceCheck(
        account=quote.recipient,
        asset_id=token.asset_id,
        before=str(before),
        after=str(after),
        delta=str(delta),
        required=str(required),
        verified=verified,
        checked_at=iso_utc(now) or "",
        error=error,
        baseline_observation_id=baseline_observation_id,
        after_block_height=after_read.block_height if after_read else None,
        after_block_hash=after_read.block_hash if after_read else None,
        after_finality=after_read.finality if after_read else None,
        after_rpc_source=after_read.rpc_source if after_read else None,
    )


def make_reader(config: IntentsConfig) -> NearRpcClient:
    return NearRpcClient(
        rpc_url=config.rpc_url,
        timeout_seconds=config.request_timeout_seconds,
    )
