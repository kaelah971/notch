"""S2 contract interface, onchain reads and resolution-plan preparation.

No transaction is signed or submitted by this module.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from datetime import date, datetime
from typing import Any

from services.trend_radar.canonical import sha256_text
from services.trend_radar.models import iso_utc, now_utc

from .evidence import verify_evidence
from .models import PLAN_SCHEMA, ResolutionPlan
from .rules import day_end, day_start, rule_digest, to_ns, validate_rule

RPC_URL = "https://rpc.testnet.near.org"
DEFAULT_CONTRACT = "market.notch-dev.testnet"
GAS_TGAS = 100
DEPOSIT_YOCTO = 0


class ContractReadError(RuntimeError):
    pass


class ResolutionConflict(RuntimeError):
    pass


class NearRpcClient:
    def __init__(
        self,
        *,
        rpc_url: str = RPC_URL,
        contract_id: str = DEFAULT_CONTRACT,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.rpc_url = rpc_url
        self.contract_id = contract_id
        self.timeout_seconds = timeout_seconds

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            self.rpc_url,
            data=json.dumps(
                {"jsonrpc": "2.0", "id": "s3b", "method": method, "params": params}
            ).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ContractReadError(f"NEAR RPC error: {exc}") from exc
        if "error" in payload:
            raise ContractReadError(json.dumps(payload["error"])[:500])
        return payload["result"]

    def view(self, method: str, args: dict[str, Any]) -> Any:
        params = {
            "request_type": "call_function",
            "finality": "final",
            "account_id": self.contract_id,
            "method_name": method,
            "args_base64": base64.b64encode(
                json.dumps(args, separators=(",", ":")).encode("utf-8")
            ).decode("ascii"),
        }
        result = self._rpc("query", params)
        raw = bytes(result.get("result", []))
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def get_market(self, market_id: str) -> dict[str, Any] | None:
        return self.view("get_market", {"market_id": market_id})

    def get_contract_config(self) -> dict[str, Any]:
        return self.view("get_contract_config", {})

    def get_market_count(self) -> int:
        value = self.view("get_market_count", {})
        return int(value or 0)

    def latest_block_timestamp_ns(self) -> int:
        result = self._rpc("block", {"finality": "final"})
        return int(result["header"]["timestamp"])


def _parse_ns(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def validate_market_against_rule(
    rule: dict[str, Any],
    market: dict[str, Any],
    *,
    contract_config: dict[str, Any] | None,
    contract_account: str,
    now_ns: int,
) -> tuple[list[str], list[str], str]:
    blockers: list[str] = []
    warnings: list[str] = []
    if market is None:
        return ["MARKET_NOT_FOUND"], [], "BLOCKED"
    if market.get("market_id") != rule.get("market_id"):
        blockers.append("MARKET_ID_MISMATCH")
    if market.get("mode") != rule.get("mode"):
        blockers.append("MODE_MISMATCH")
    if market.get("source_id") != rule.get("source", {}).get("id"):
        blockers.append("SOURCE_MISMATCH")
    if market.get("rule_hash") != rule_digest(rule):
        blockers.append("RULE_HASH_MISMATCH")
    if market.get("question") != rule.get("question"):
        blockers.append("QUESTION_MISMATCH")
    if list(market.get("choices") or []) != list(rule.get("choices") or []):
        blockers.append("CHOICES_MISMATCH")
    if str(market.get("open_at")) != str(rule["market_timing"]["open_at_ns"]):
        blockers.append("OPEN_AT_MISMATCH")
    if str(market.get("close_at")) != str(rule["market_timing"]["close_at_ns"]):
        blockers.append("CLOSE_AT_MISMATCH")
    if str(market.get("resolve_after")) != str(rule["market_timing"]["resolve_after_ns"]):
        blockers.append("RESOLVE_AFTER_MISMATCH")
    if contract_account != rule.get("contract", {}).get("account"):
        blockers.append("CONTRACT_ACCOUNT_MISMATCH")
    if contract_config and contract_config.get("collateral_token") != rule.get(
        "contract", {}
    ).get("collateral_token"):
        blockers.append("COLLATERAL_TOKEN_MISMATCH")

    if rule.get("mode") == "trend_battle":
        battle = market.get("battle")
        if not isinstance(battle, dict):
            blockers.append("BATTLE_CONFIG_MISSING")
        else:
            rule_topics = rule.get("topics", [])
            view_topics = [battle.get("topic_a") or {}, battle.get("topic_b") or {}]
            for index, (view_topic, rule_topic) in enumerate(zip(view_topics, rule_topics)):
                if view_topic.get("article_title") != rule_topic.get("article_title"):
                    blockers.append(f"BATTLE_TOPIC_{index}_MISMATCH")
                if view_topic.get("topic_id") != rule_topic.get("topic_id"):
                    blockers.append(f"BATTLE_TOPIC_ID_{index}_MISMATCH")
                if view_topic.get("source_id") != rule.get("source", {}).get("id"):
                    blockers.append(f"BATTLE_TOPIC_SOURCE_{index}_MISMATCH")
            if battle.get("formula") != "growth_comparison_v1":
                blockers.append("BATTLE_FORMULA_MISMATCH")
            if int(battle.get("tie_tolerance_bps", -1)) != int(
                rule["formula"]["tie_tolerance_bps"]
            ):
                blockers.append("TIE_TOLERANCE_MISMATCH")
            if battle.get("tie_policy") != "void":
                blockers.append("TIE_POLICY_MISMATCH")
            baseline = rule["observation"]["baseline_date"]
            target = rule["observation"]["target_date"]
            expected_start = str(to_ns(day_start(date.fromisoformat(baseline))))
            expected_end = str(to_ns(day_end(date.fromisoformat(target))))
            if str(battle.get("observation_start")) != expected_start:
                blockers.append("OBSERVATION_START_MISMATCH")
            if str(battle.get("observation_end")) != expected_end:
                blockers.append("OBSERVATION_END_MISMATCH")
            if int(battle.get("min_baseline_views", -1)) != int(
                rule["minimum_baseline_views"]
            ):
                blockers.append("MIN_BASELINE_MISMATCH")

    status = market.get("status")
    if status in {"resolved", "voided"}:
        return [], warnings, "ALREADY_FINAL"
    if now_ns < _parse_ns(market.get("resolve_after"), "resolve_after"):
        blockers.append("RESOLVE_TOO_EARLY")
    if status not in {"open", "closed"}:
        blockers.append(f"MARKET_STATUS_NOT_RESOLVABLE:{status}")
    return blockers, warnings, "BLOCKED" if blockers else "READY"


def _action_for(rule: dict[str, Any], evidence: dict[str, Any]) -> str:
    outcome = evidence.get("outcome")
    if outcome == "INVALID":
        return "void_market"
    if rule["mode"] == "trend_trading":
        return "resolve_market" if outcome in {"UP", "DOWN"} else "void_market"
    if outcome == "TIE":
        return "resolve_tie"
    if outcome in {"TOPIC_A", "TOPIC_B"}:
        return "resolve_market"
    return "void_market"


def _contract_call(
    rule: dict[str, Any], evidence: dict[str, Any], action: str
) -> dict[str, Any]:
    digest = evidence["evidence_digest"]
    if action == "resolve_market":
        outcome = (
            0 if evidence["outcome"] in {"UP", "TOPIC_A"} else 1
        )
        args = {
            "market_id": rule["market_id"],
            "winning_outcome": outcome,
            "evidence_hash": digest,
        }
    elif action == "resolve_tie":
        args = {"market_id": rule["market_id"], "evidence_hash": digest}
    elif action == "void_market":
        args = {"market_id": rule["market_id"], "reason_hash": digest}
    else:
        raise ValueError(f"unsupported action: {action}")
    return {
        "contract_id": rule["contract"]["account"],
        "method": action,
        "args": args,
        "gas_tgas": GAS_TGAS,
        "deposit_yocto": DEPOSIT_YOCTO,
    }


def _near_cli_template(call: dict[str, Any]) -> str:
    args_json = json.dumps(call["args"], separators=(",", ":"), ensure_ascii=False)
    return (
        "near contract call-function as-transaction "
        f"{call['contract_id']} {call['method']} json-args '{args_json}' "
        f"prepaid-gas '{call['gas_tgas']} Tgas' attached-deposit '0 NEAR' "
        "sign-as <resolver-account> network-config testnet sign-with-keychain send"
    )


def job_id_for(rule_hash: str, evidence_digest: str, action: str, market_id: str) -> str:
    return "job_" + sha256_text(
        f"{market_id}:{rule_hash}:{evidence_digest}:{action}"
    )[:20]


def prepare_resolution(
    rule_record: dict[str, Any],
    evidence: dict[str, Any],
    *,
    market: dict[str, Any] | None = None,
    contract_config: dict[str, Any] | None = None,
    contract_account: str = DEFAULT_CONTRACT,
    now: datetime | None = None,
    now_ns: int | None = None,
) -> ResolutionPlan:
    now = now or now_utc()
    if now_ns is None:
        now_ns = int(now.timestamp()) * 1_000_000_000
    rule = rule_record.get("rule", rule_record)
    rule_hash = rule_digest(rule)
    blockers: list[str] = []
    warnings: list[str] = []
    rule_errors = validate_rule(rule)
    if rule_errors:
        blockers.extend(f"RULE_INVALID:{error}" for error in rule_errors)
    if rule_record.get("status") != "APPROVED":
        blockers.append("RULE_NOT_APPROVED")
    verification = verify_evidence(evidence, expected_rule_hash=rule_hash)
    if not verification["valid"]:
        blockers.extend(f"EVIDENCE_INVALID:{reason}" for reason in verification["reasons"])
    if evidence.get("market_id") != rule.get("market_id"):
        blockers.append("EVIDENCE_MARKET_MISMATCH")
    if evidence.get("rule_hash") != rule_hash:
        blockers.append("EVIDENCE_RULE_MISMATCH")

    action = _action_for(rule, evidence)
    if action == "void_market" and evidence.get("outcome") != "INVALID":
        blockers.append("NON_INVALID_OUTCOME_MAPPED_TO_VOID")
    if evidence.get("outcome") == "INVALID" and action != "void_market":
        blockers.append("INVALID_OUTCOME_MUST_VOID")

    call = _contract_call(rule, evidence, action)
    status = "BLOCKED" if blockers else "PREPARED"
    if market is not None:
        market_blockers, market_warnings, market_status = validate_market_against_rule(
            rule,
            market,
            contract_config=contract_config,
            contract_account=contract_account,
            now_ns=now_ns,
        )
        blockers.extend(market_blockers)
        warnings.extend(market_warnings)
        if market_status == "ALREADY_FINAL" and not blockers:
            status = "ALREADY_FINAL"
            call = None
        else:
            status = "BLOCKED" if blockers else "PREPARED"
    else:
        blockers.append("ONCHAIN_MARKET_NOT_PROVIDED")
        status = "BLOCKED"

    if market is not None and action == "resolve_market":
        outcome_index = 0 if evidence["outcome"] in {"UP", "TOPIC_A"} else 1
        totals = market.get("totals") or ["0", "0"]
        try:
            winning_stake = int(totals[outcome_index])
        except (ValueError, TypeError, IndexError):
            winning_stake = 0
        if winning_stake == 0:
            warnings.append(
                "NO_WINNING_STAKE: void_market must be used instead of resolve_market"
            )
            action = "void_market"
            call = _contract_call(rule, evidence, action)
            if status == "PREPARED":
                status = "PREPARED"

    plan = ResolutionPlan(
        schema_version=PLAN_SCHEMA,
        job_id=job_id_for(rule_hash, evidence["evidence_digest"], action, rule["market_id"]),
        market_id=rule["market_id"],
        rule_hash=rule_hash,
        mode=rule["mode"],
        evidence_digest=evidence["evidence_digest"],
        outcome=evidence["outcome"],
        action=action,
        status=status,
        contract_call=call,
        near_cli_command_template=_near_cli_template(call) if call else None,
        blockers=sorted(set(blockers)),
        warnings=warnings,
        onchain_market=market,
        prepared_at=iso_utc(now),
    )
    return plan
