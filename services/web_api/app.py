"""S6 frontend-ready HTTP API over existing Notch services."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from services.intents.balance import NearRpcClient, NearRpcError
from services.intents.client import TidepoolClient, TidepoolError
from services.intents.config import IntentsConfig
from services.intents.models import DepositType
from services.intents.service import IntentsFundingService
from services.intents.store import FundingStore, FundingStoreError
from services.intents.validation import ValidationError, is_near_account, parse_base_units
from services.near_ai.client import NearAIClient, NearAIError
from services.near_ai.config import NearAIConfig
from services.near_ai.grounding import GroundingError
from services.near_ai.service import BriefService
from services.near_ai.store import BriefStore
from services.oracle.evidence import verify_evidence
from services.trend_radar.models import iso_utc, now_utc, parse_iso
from services.web_api.chain import ChainReadError, MarketChainReader
from services.web_api.config import WebAPIConfig
from services.web_api.predictions import classify_prediction
from services.web_api.repositories import OracleRepository, RadarRepository, RepositoryError
from services.web_api.schemas import (
    ApiError,
    EntryIntent,
    MarketSummary,
    PositionSummary,
    TokenBalance,
)


class RateLimiter:
    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, client: str, category: str, limit_per_minute: int) -> None:
        if limit_per_minute <= 0:
            return
        now = self.clock()
        bucket = self.events[(client, category)]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit_per_minute:
            raise ApiError(
                "RATE_LIMITED",
                "too many requests; retry later",
                status=429,
                details={"category": category, "limit_per_minute": limit_per_minute},
            )
        bucket.append(now)


class WebAPI:
    def __init__(
        self,
        *,
        config: WebAPIConfig,
        chain: MarketChainReader,
        radar: RadarRepository,
        oracle: OracleRepository,
        brief_service: BriefService,
        funding_service: IntentsFundingService,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.config = config
        self.chain = chain
        self.radar = radar
        self.oracle = oracle
        self.brief_service = brief_service
        self.funding_service = funding_service
        self.rate_limiter = rate_limiter or RateLimiter()

    def close(self) -> None:
        self.brief_service.store.close()
        self.funding_service.store.close()

    # ------------------------------------------------------------------
    # Request boundary
    # ------------------------------------------------------------------
    def handle(
        self,
        method: str,
        raw_path: str,
        query: dict[str, str],
        body: Any,
        client: str = "local",
    ) -> tuple[int, dict[str, Any]]:
        try:
            self.rate_limiter.check(
                client, "general", self.config.general_rate_limit_per_minute
            )
            path = raw_path.rstrip("/") or "/"
            parts = [unquote(item) for item in path.split("/") if item]
            if method == "GET":
                return self._get(parts, query)
            if method == "POST":
                return self._post(parts, query, body)
            raise ApiError("METHOD_NOT_ALLOWED", "method not allowed", status=405)
        except ApiError as exc:
            return exc.status, exc.to_dict()
        except ValidationError as exc:
            return 400, ApiError(
                exc.code, str(exc), status=400, details={"field": exc.field}
            ).to_dict()
        except (ChainReadError, NearRpcError, RepositoryError, NearAIError, GroundingError, TidepoolError) as exc:
            return 503, ApiError(
                "DEPENDENCY_UNAVAILABLE", str(exc), status=503
            ).to_dict()
        except FundingStoreError as exc:
            return 404, ApiError("QUOTE_NOT_FOUND", str(exc), status=404).to_dict()
        except Exception:
            return 500, ApiError(
                "INTERNAL_ERROR", "the API could not complete the request", status=500
            ).to_dict()

    def _get(self, parts: list[str], query: dict[str, str]) -> tuple[int, dict[str, Any]]:
        if parts == ["api", "health"]:
            return 200, {"data": self.health()}
        if parts == ["api", "briefs", "status"]:
            return 200, {"data": self.brief_service.status()}
        if parts == ["api", "trends"]:
            return 200, self._trends()
        if len(parts) == 3 and parts[:2] == ["api", "trends"]:
            return 200, {"data": self._trend_detail(parts[2])}
        if len(parts) == 4 and parts[:2] == ["api", "trends"] and parts[3] == "brief":
            return 200, self._trend_brief(parts[2])
        if parts == ["api", "markets"]:
            return 200, self._markets()
        if len(parts) == 3 and parts[:2] == ["api", "markets"]:
            return 200, {"data": self._market_detail(parts[2])}
        if len(parts) == 4 and parts[:2] == ["api", "markets"] and parts[3] == "evidence":
            return 200, self._market_evidence(parts[2])
        if len(parts) == 4 and parts[:2] == ["api", "markets"] and parts[3] == "brief":
            return 200, self._market_brief(parts[2])
        if parts == ["api", "funding", "tokens"]:
            return 200, self._funding_tokens()
        if len(parts) == 4 and parts[:2] == ["api", "funding"] and parts[2] == "status":
            return 200, self._funding_status(parts[3], query)
        if parts == ["api", "funding", "readiness"]:
            return 200, self._funding_readiness(query)
        if len(parts) == 4 and parts[:2] == ["api", "wallets"] and parts[3] == "balances":
            return 200, self._wallet_balances(parts[2])
        if len(parts) == 4 and parts[:2] == ["api", "wallets"] and parts[3] == "positions":
            return 200, self._wallet_positions(parts[2])
        raise ApiError("NOT_FOUND", "endpoint not found", status=404)

    def _post(
        self, parts: list[str], query: dict[str, str], body: Any
    ) -> tuple[int, dict[str, Any]]:
        if not isinstance(body, dict):
            raise ApiError("INVALID_BODY", "JSON object body is required", status=400)
        if parts == ["api", "funding", "quote"]:
            return 200, self._funding_quote(body)
        if len(parts) == 4 and parts[:2] == ["api", "markets"] and parts[3] == "entry-intent":
            return 200, self._entry_intent(parts[2], body)
        raise ApiError("NOT_FOUND", "endpoint not found", status=404)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        degraded = False
        try:
            market_count = self.chain.get_market_count()
            now_ns = self.chain.now_ns()
            contract_config = self.chain.get_contract_config()
            checks["near_rpc"] = {
                "ok": True,
                "market_count": market_count,
                "block_timestamp_ns": str(now_ns),
                "block_time": _ns_to_iso(now_ns),
            }
            checks["market_contract"] = {
                "ok": True,
                "contract": self.config.market_contract,
                "collateral_token": contract_config.get("collateral_token"),
                "min_entry_amount": str(contract_config.get("min_entry_amount")),
                "entries_paused": bool(contract_config.get("entries_paused")),
            }
        except Exception as exc:
            degraded = True
            checks["near_rpc"] = {"ok": False, "error": type(exc).__name__}
        checks["radar_db"] = {
            "ok": Path(self.config.radar_db).exists(),
            "path": self.config.radar_db,
        }
        checks["oracle_dbs"] = [
            {"path": path, "ok": Path(path).exists()} for path in self.config.oracle_db_paths
        ]
        checks["briefs"] = {
            "ok": True,
            "cache_count": self.brief_service.store.count(),
            "ai_key_present": self.brief_service.config.key_present,
            "ai_model": self.brief_service.config.model,
        }
        checks["funding"] = {
            "ok": True,
            "provider": "tidepool-testnet",
            "data_dir": self.funding_service.config.data_dir,
        }
        if not all(
            [
                checks["radar_db"]["ok"],
                any(item["ok"] for item in checks["oracle_dbs"]),
            ]
        ):
            degraded = True
        return {
            "status": "degraded" if degraded else "ok",
            "network": self.config.network,
            "checks": checks,
            "checked_at": iso_utc(now_utc()),
        }

    # ------------------------------------------------------------------
    # Radar
    # ------------------------------------------------------------------
    def _trends(self) -> dict[str, Any]:
        now = now_utc()
        items = self.radar.list_candidates(limit=50)
        data = [self.radar.summary(item, now=now) for item in items]
        return {"data": data, "meta": {"count": len(data), "eligibility": "ELIGIBLE"}}

    def _trend_detail(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.radar.get_candidate(candidate_id)
        if candidate is None:
            raise ApiError("TREND_NOT_FOUND", f"unknown candidate: {candidate_id}", status=404)
        return self.radar.detail(candidate, now=now_utc())

    def _trend_brief(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.radar.get_candidate(candidate_id)
        if candidate is None:
            raise ApiError("TREND_NOT_FOUND", f"unknown candidate: {candidate_id}", status=404)
        brief = self.brief_service.radar_brief(candidate_id, allow_ai=False)
        return {
            "data": brief.to_dict(),
            "meta": {
                "candidate_id": candidate_id,
                "generation_mode": "cached_or_deterministic",
                "ai_call_triggered": False,
            },
        }

    # ------------------------------------------------------------------
    # Markets
    # ------------------------------------------------------------------
    def _markets(self) -> dict[str, Any]:
        now_ns = self.chain.now_ns()
        markets = self.chain.list_markets()
        data = []
        for market in markets:
            rule, evidence = self.oracle.find(str(market.get("market_id")))
            data.append(
                self._market_summary(market, now_ns, rule=rule, evidence=evidence).to_dict()
            )
        return {"data": data, "meta": {"count": len(data), "network": self.config.network}}

    def _market_detail(self, market_id: str) -> dict[str, Any]:
        market = self.chain.get_market(market_id)
        if market is None:
            raise ApiError("MARKET_NOT_FOUND", f"unknown market: {market_id}", status=404)
        now_ns = self.chain.now_ns()
        rule, evidence = self.oracle.find(market_id)
        summary = self._market_summary(market, now_ns, rule=rule, evidence=evidence)
        totals = self.chain.get_market_totals(market_id)
        contract_config = self.chain.get_contract_config()
        data = summary.to_dict()
        data["onchain"] = market
        data["totals_view"] = totals
        data["contract_config"] = contract_config
        data["rule"] = rule.get("rule") if rule else None
        data["rule_record"] = (
            {
                "rule_hash": rule.get("rule_hash"),
                "status": rule.get("status"),
                "created_at": rule.get("created_at"),
                "approved_by": rule.get("approved_by"),
                "approved_at": rule.get("approved_at"),
            }
            if rule
            else None
        )
        data["evidence_digest"] = evidence.get("evidence_digest") if evidence else None
        evidence_verified = False
        if evidence:
            try:
                evidence_verified = bool(
                    verify_evidence(
                        evidence, expected_rule_hash=market.get("rule_hash", "")
                    ).get("valid")
                )
            except Exception:
                evidence_verified = False
        data["evidence_verified"] = evidence_verified
        return data

    def _market_evidence(self, market_id: str) -> dict[str, Any]:
        market = self.chain.get_market(market_id)
        if market is None:
            raise ApiError("MARKET_NOT_FOUND", f"unknown market: {market_id}", status=404)
        result = self.oracle.verify(market_id)
        if result is None:
            raise ApiError(
                "EVIDENCE_NOT_AVAILABLE",
                "no canonical rule or evidence receipt is stored for this market",
                status=404,
            )
        return {
            "data": result,
            "meta": {
                "market_id": market_id,
                "onchain_rule_hash": market.get("rule_hash"),
                "onchain_evidence_hash": market.get("evidence_hash"),
            },
        }

    def _market_brief(self, market_id: str) -> dict[str, Any]:
        market = self.chain.get_market(market_id)
        if market is None:
            raise ApiError("MARKET_NOT_FOUND", f"unknown market: {market_id}", status=404)
        rule, evidence = self.oracle.find(market_id)
        if rule is None or evidence is None:
            raise ApiError(
                "EVIDENCE_NOT_AVAILABLE",
                "a rule and evidence receipt are required for a market brief",
                status=404,
            )
        brief = self.brief_service.market_brief_from_records(
            rule, evidence, allow_ai=False
        )
        summary = self._market_summary(market, self.chain.now_ns(), rule=rule, evidence=evidence)
        return {
            "data": {
                "brief": brief.to_dict(),
                "market": summary.to_dict(),
            },
            "meta": {
                "market_id": market_id,
                "generation_mode": "cached_or_deterministic",
                "ai_call_triggered": False,
            },
        }

    def _market_summary(
        self,
        market: dict[str, Any],
        now_ns: int,
        *,
        rule: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> MarketSummary:
        rule_body = rule.get("rule") if rule else {}
        question = str(market.get("question") or "")
        replay = bool(rule_body.get("observation", {}).get("replay")) or (
            "HISTORICAL REPLAY" in question.upper()
        )
        future = (not replay) if rule_body else question.upper().startswith("FORECAST")
        status = str(market.get("status") or "unknown")
        if status == "voided":
            display = "voided"
        elif replay:
            display = f"historical_replay_{status}"
        elif status == "open":
            display = "open_future"
        else:
            display = status
        close_at = int(market.get("close_at") or 0)
        resolve_after = int(market.get("resolve_after") or 0)
        return MarketSummary(
            market_id=str(market.get("market_id")),
            mode=str(market.get("mode")),
            question=question,
            choices=list(market.get("choices") or []),
            source_id=str(market.get("source_id")),
            rule_hash=str(market.get("rule_hash")),
            status=status,
            display_status=display,
            is_historical_replay=replay,
            is_future_prediction=future,
            entries_open=bool(market.get("entries_open")),
            entries_paused=bool(market.get("entries_paused")),
            open_at=str(market.get("open_at")),
            close_at=str(market.get("close_at")),
            resolve_after=str(market.get("resolve_after")),
            open_at_utc=_ns_to_iso(int(market.get("open_at") or 0)),
            close_at_utc=_ns_to_iso(int(market.get("close_at") or 0)),
            resolve_after_utc=_ns_to_iso(int(market.get("resolve_after") or 0)),
            resolution_eligible=now_ns >= resolve_after,
            totals=[str(item) for item in market.get("totals") or []],
            escrow_total=str(market.get("escrow_total")),
            paid_total=str(market.get("paid_total")),
            unclaimed_reserve=str(market.get("unclaimed_reserve")),
            winning_outcome=market.get("winning_outcome"),
            winning_choice=market.get("winning_choice"),
            evidence_hash=market.get("evidence_hash"),
            resolution_kind=market.get("resolution_kind"),
            created_at=market.get("created_at"),
            resolved_at=market.get("resolved_at"),
            created_at_utc=_optional_ns_iso(market.get("created_at")),
            resolved_at_utc=_optional_ns_iso(market.get("resolved_at")),
            battle=market.get("battle"),
            rule_available=rule is not None,
            evidence_available=evidence is not None,
        )

    # ------------------------------------------------------------------
    # Funding
    # ------------------------------------------------------------------
    def _funding_tokens(self) -> dict[str, Any]:
        self.rate_limiter.check(
            "funding", "funding-tokens", self.config.quote_rate_limit_per_minute
        )
        tokens = self.funding_service.discover_tokens()
        routes = self.funding_service.supported_routes()
        return {
            "data": {
                "tokens": [token.to_dict() for token in tokens],
                "routes": [route.to_dict() for route in routes],
                "destination_asset": self.funding_service.config.destination_asset,
            }
        }

    def _funding_quote(self, body: dict[str, Any]) -> dict[str, Any]:
        self.rate_limiter.check(
            "funding", "funding-quote", self.config.quote_rate_limit_per_minute
        )
        allowed = {
            "source_asset",
            "amount",
            "recipient",
            "refund_to",
            "deposit_type",
            "slippage_bps",
            "deadline_minutes",
            "dry",
        }
        unknown = set(body) - allowed
        if unknown:
            raise ApiError(
                "INVALID_BODY",
                f"unsupported fields: {', '.join(sorted(unknown))}",
                status=400,
            )
        for field in ("source_asset", "amount", "recipient"):
            if not isinstance(body.get(field), str) or not body[field]:
                raise ApiError("INVALID_BODY", f"{field} is required", status=400)
        dry_value = body.get("dry", False)
        if not isinstance(dry_value, bool):
            raise ApiError("INVALID_BODY", "dry must be a boolean", status=400)
        dry = dry_value
        deposit_type = str(body.get("deposit_type") or DepositType.INTENTS.value)
        try:
            deadline_minutes = int(body.get("deadline_minutes") or 30)
        except (TypeError, ValueError) as exc:
            raise ApiError("INVALID_BODY", "deadline_minutes must be an integer", status=400) from exc
        if deadline_minutes < 1 or deadline_minutes > 60:
            raise ApiError("INVALID_BODY", "deadline_minutes must be 1-60", status=400)
        slippage = body.get("slippage_bps")
        if slippage is not None:
            try:
                slippage = int(slippage)
            except (TypeError, ValueError) as exc:
                raise ApiError("INVALID_BODY", "slippage_bps must be an integer", status=400) from exc
        if dry:
            prepared = self.funding_service.dry_quote(
                source_asset=body["source_asset"],
                amount=body["amount"],
                recipient=body["recipient"],
                refund_to=body.get("refund_to"),
                deposit_type=deposit_type,
                slippage_bps=slippage,
                deadline_minutes=deadline_minutes,
            )
        else:
            prepared = self.funding_service.prepare_swap(
                source_asset=body["source_asset"],
                amount=body["amount"],
                recipient=body["recipient"],
                refund_to=body.get("refund_to"),
                deposit_type=deposit_type,
                slippage_bps=slippage,
                deadline_minutes=deadline_minutes,
            )
        return {
            "data": prepared.to_dict(),
            "meta": {"signed": False, "broadcast": False, "dry": dry},
        }

    def _funding_status(self, quote_id: str, query: dict[str, str]) -> dict[str, Any]:
        quote = self.funding_service.get_quote(quote_id)
        if query.get("refresh") == "true":
            quote = self.funding_service.refresh_status(quote_id, max_attempts=1)
        return {"data": self.funding_service.quote_summary(quote)}

    def _funding_readiness(self, query: dict[str, str]) -> dict[str, Any]:
        account = query.get("account_id")
        if not account or not is_near_account(account):
            raise ApiError("INVALID_ACCOUNT", "valid account_id is required", status=400)
        return {"data": self.funding_service.get_available_collateral(account)}

    # ------------------------------------------------------------------
    # Wallets
    # ------------------------------------------------------------------
    def _wallet_balances(self, account_id: str) -> dict[str, Any]:
        if not is_near_account(account_id):
            raise ApiError("INVALID_ACCOUNT", "invalid NEAR account ID", status=400)
        config = self.funding_service.config
        tokens: list[TokenBalance] = []
        for contract, symbol in (
            (config.destination_asset.removeprefix("nep141:"), "USDC"),
            ("usdt.tidepool-sandbox.testnet", "USDT"),
        ):
            metadata = self.chain.ft_metadata(contract)
            storage = self.chain.storage_balance(contract, account_id)
            tokens.append(
                TokenBalance(
                    asset_id=f"nep141:{contract}",
                    contract=contract,
                    symbol=str(metadata.get("symbol") or symbol),
                    decimals=int(metadata.get("decimals") or 0),
                    balance=self.chain.ft_balance(contract, account_id),
                    storage_registered=storage is not None,
                    storage_total=(storage or {}).get("total"),
                    name=metadata.get("name"),
                )
            )
        contract_config = self.chain.get_contract_config()
        usdc = next(item for item in tokens if item.symbol == "USDC")
        return {
            "data": {
                "account_id": account_id,
                "network": self.config.network,
                "near": {
                    "yocto_near": self.chain.native_balance(account_id),
                    "decimals": 24,
                },
                "tokens": [item.to_dict() for item in tokens],
                "collateral": {
                    "contract": contract_config.get("collateral_token"),
                    "asset_id": usdc.asset_id,
                    "decimals": usdc.decimals,
                    "balance": usdc.balance,
                    "storage_registered": usdc.storage_registered,
                    "min_entry_amount": str(contract_config.get("min_entry_amount")),
                    "ready": usdc.storage_registered
                    and int(usdc.balance) >= int(contract_config.get("min_entry_amount") or 0),
                },
            }
        }

    def _wallet_positions(self, account_id: str) -> dict[str, Any]:
        if not is_near_account(account_id):
            raise ApiError("INVALID_ACCOUNT", "invalid NEAR account ID", status=400)
        positions: list[PositionSummary] = []
        for market in self.chain.list_markets():
            market_id = str(market.get("market_id"))
            position = self.chain.get_position(market_id, account_id)
            if position is None:
                continue
            result = classify_prediction(market, position)
            positions.append(
                PositionSummary(
                    market_id=market_id,
                    mode=str(market.get("mode")),
                    question=str(market.get("question")),
                    market_status=str(market.get("status")),
                    winning_choice=market.get("winning_choice"),
                    stakes=[str(item) for item in position.get("stakes") or []],
                    total_stake=str(position.get("total_stake")),
                    claimed_total=str(position.get("claimed_total")),
                    pending_amount=str(position.get("pending_amount")),
                    claimable=str(position.get("claimable")),
                    claim_state=str(position.get("claim_state")),
                    prediction_status=result["status"],
                    prediction_choice=result["choice"],
                    prediction_choices=result["choices"],
                    evidence_hash=market.get("evidence_hash"),
                    resolution_kind=market.get("resolution_kind"),
                )
            )
        return {
            "data": [item.to_dict() for item in positions],
            "meta": {"account_id": account_id, "count": len(positions)},
        }

    # ------------------------------------------------------------------
    # Entry intent
    # ------------------------------------------------------------------
    def _entry_intent(self, market_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.rate_limiter.check(
            "entry", "entry-intent", self.config.entry_rate_limit_per_minute
        )
        allowed = {"account_id", "side", "stake"}
        unknown = set(body) - allowed
        if unknown:
            raise ApiError(
                "INVALID_BODY",
                f"unsupported fields: {', '.join(sorted(unknown))}",
                status=400,
            )
        account_id = body.get("account_id")
        if not isinstance(account_id, str) or not is_near_account(account_id):
            raise ApiError("INVALID_ACCOUNT", "valid account_id is required", status=400)
        stake = parse_base_units(body.get("stake"), field="stake")
        market = self.chain.get_market(market_id)
        if market is None:
            raise ApiError("MARKET_NOT_FOUND", f"unknown market: {market_id}", status=404)
        contract_config = self.chain.get_contract_config()
        now_ns = self.chain.now_ns()
        if contract_config.get("entries_paused"):
            raise ApiError("ENTRIES_PAUSED", "market entries are paused", status=409)
        if market.get("status") != "open" or not market.get("entries_open"):
            raise ApiError(
                "MARKET_NOT_OPEN",
                f"market is {market.get('status')} and is not accepting entries",
                status=409,
            )
        close_at = int(market.get("close_at") or 0)
        if close_at <= now_ns:
            raise ApiError("ENTRY_CLOSED", "the entry deadline has passed", status=409)
        choices = list(market.get("choices") or [])
        side = body.get("side")
        if isinstance(side, bool):
            raise ApiError("INVALID_SIDE", "side must be an outcome index or choice", status=400)
        if isinstance(side, int):
            outcome = side
        elif isinstance(side, str):
            if side.isdigit():
                outcome = int(side)
            elif side in choices:
                outcome = choices.index(side)
            else:
                raise ApiError("INVALID_SIDE", "side does not match a market choice", status=400)
        else:
            raise ApiError("INVALID_SIDE", "side is required", status=400)
        if outcome < 0 or outcome >= len(choices):
            raise ApiError("INVALID_SIDE", "side is outside the market choices", status=400)
        min_entry = int(contract_config.get("min_entry_amount") or 0)
        if stake < min_entry:
            raise ApiError(
                "STAKE_BELOW_MINIMUM",
                f"stake must be at least {min_entry} base units",
                status=400,
            )
        collateral = str(contract_config.get("collateral_token") or "")
        if collateral != self.config.collateral_token:
            raise ApiError(
                "COLLATERAL_MISMATCH",
                "market collateral does not match the configured collateral",
                status=409,
            )
        storage = self.chain.storage_balance(collateral, account_id)
        if storage is None:
            raise ApiError(
                "COLLATERAL_STORAGE_NOT_REGISTERED",
                "wallet is not registered for the collateral token",
                status=409,
            )
        balance = int(self.chain.ft_balance(collateral, account_id))
        if balance < stake:
            raise ApiError(
                "INSUFFICIENT_COLLATERAL",
                "wallet balance is below the requested stake",
                status=409,
                details={"balance": str(balance), "stake": str(stake)},
            )
        msg = json.dumps(
            {"market_id": market_id, "outcome": outcome},
            separators=(",", ":"),
        )
        intent = EntryIntent(
            network=self.config.network,
            signer=account_id,
            receiver=collateral,
            method="ft_transfer_call",
            args={
                "receiver_id": self.config.market_contract,
                "amount": str(stake),
                "msg": msg,
            },
            attached_deposit_yocto="1",
            gas_tgas=100,
            market_id=market_id,
            outcome=outcome,
            choice=str(choices[outcome]),
            stake=str(stake),
            collateral_token=collateral,
            min_entry_amount=str(min_entry),
            expected={
                "market_id": market_id,
                "outcome": outcome,
                "choice": str(choices[outcome]),
                "stake": str(stake),
                "collateral": collateral,
                "fee_bps": contract_config.get("fee_bps"),
            },
        )
        return {
            "data": intent.to_dict(),
            "meta": {"signed": False, "broadcast": False},
        }


def _ns_to_iso(value: int) -> str:
    import datetime

    return (
        datetime.datetime.fromtimestamp(value / 1e9, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _optional_ns_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return _ns_to_iso(int(value))
    except (TypeError, ValueError):
        return None
