"""Typed response and error schemas for the S6 web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ApiError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


@dataclass
class MarketSummary:
    market_id: str
    mode: str
    question: str
    choices: list[str]
    source_id: str
    rule_hash: str
    status: str
    display_status: str
    is_historical_replay: bool
    is_future_prediction: bool
    entries_open: bool
    entries_paused: bool
    open_at: str
    close_at: str
    resolve_after: str
    open_at_utc: str
    close_at_utc: str
    resolve_after_utc: str
    resolution_eligible: bool
    totals: list[str]
    escrow_total: str
    paid_total: str
    unclaimed_reserve: str
    winning_outcome: int | None
    winning_choice: str | None
    evidence_hash: str | None
    resolution_kind: str | None
    created_at: str | None
    resolved_at: str | None
    created_at_utc: str | None
    resolved_at_utc: str | None
    battle: dict[str, Any] | None = None
    rule_available: bool = False
    evidence_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "mode": self.mode,
            "question": self.question,
            "choices": self.choices,
            "source_id": self.source_id,
            "rule_hash": self.rule_hash,
            "status": self.status,
            "display_status": self.display_status,
            "is_historical_replay": self.is_historical_replay,
            "is_future_prediction": self.is_future_prediction,
            "entries_open": self.entries_open,
            "entries_paused": self.entries_paused,
            "open_at": self.open_at,
            "close_at": self.close_at,
            "resolve_after": self.resolve_after,
            "open_at_utc": self.open_at_utc,
            "close_at_utc": self.close_at_utc,
            "resolve_after_utc": self.resolve_after_utc,
            "resolution_eligible": self.resolution_eligible,
            "totals": self.totals,
            "escrow_total": self.escrow_total,
            "paid_total": self.paid_total,
            "unclaimed_reserve": self.unclaimed_reserve,
            "winning_outcome": self.winning_outcome,
            "winning_choice": self.winning_choice,
            "evidence_hash": self.evidence_hash,
            "resolution_kind": self.resolution_kind,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "created_at_utc": self.created_at_utc,
            "resolved_at_utc": self.resolved_at_utc,
            "battle": self.battle,
            "rule_available": self.rule_available,
            "evidence_available": self.evidence_available,
        }


@dataclass
class TokenBalance:
    asset_id: str
    contract: str
    symbol: str
    decimals: int
    balance: str
    storage_registered: bool
    storage_total: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "contract": self.contract,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "balance": self.balance,
            "storage_registered": self.storage_registered,
            "storage_total": self.storage_total,
            "name": self.name,
        }


@dataclass
class PositionSummary:
    market_id: str
    mode: str
    question: str
    market_status: str
    winning_choice: str | None
    stakes: list[str]
    total_stake: str
    claimed_total: str
    pending_amount: str
    claimable: str
    claim_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "mode": self.mode,
            "question": self.question,
            "market_status": self.market_status,
            "winning_choice": self.winning_choice,
            "stakes": self.stakes,
            "total_stake": self.total_stake,
            "claimed_total": self.claimed_total,
            "pending_amount": self.pending_amount,
            "claimable": self.claimable,
            "claim_state": self.claim_state,
        }


@dataclass
class EntryIntent:
    network: str
    signer: str
    receiver: str
    method: str
    args: dict[str, Any]
    attached_deposit_yocto: str
    gas_tgas: int
    market_id: str
    outcome: int
    choice: str
    stake: str
    collateral_token: str
    min_entry_amount: str
    expected: dict[str, Any] = field(default_factory=dict)
    signed: bool = False
    broadcast: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "network": self.network,
            "signer": self.signer,
            "receiver": self.receiver,
            "method": self.method,
            "args": self.args,
            "attached_deposit_yocto": self.attached_deposit_yocto,
            "gas_tgas": self.gas_tgas,
            "market_id": self.market_id,
            "outcome": self.outcome,
            "choice": self.choice,
            "stake": self.stake,
            "collateral_token": self.collateral_token,
            "min_entry_amount": self.min_entry_amount,
            "expected": self.expected,
            "signed": self.signed,
            "broadcast": self.broadcast,
        }
