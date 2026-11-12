#!/usr/bin/env python3
"""Prepare short-window S2.5 replay markets from verified S3B rules.

This script never broadcasts a transaction. It derives open/close/resolve times
from the current NEAR testnet block time (unless --now is explicitly supplied for
offline testing), rebuilds the exact S3B rule inputs with the existing canonical
rule builders, regenerates evidence digests, and writes exact create_market
payloads for review. Old rules/evidence remain untouched in the source store.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Allow direct execution from the repository root: python scripts/...
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.oracle.contract import NearRpcClient
from services.oracle.evidence import build_evidence, evidence_to_dict, verify_evidence
from services.oracle.fixture_fetcher import OracleFixtureFetcher
from services.oracle.review import CandidateRepository
from services.oracle.rules import (
    build_battle_rule,
    build_contract_args,
    build_trend_rule,
    market_timing,
    rule_digest,
    validate_create_args,
    validate_rule,
)
from services.oracle.store import OracleStore
from services.oracle.wikimedia import fetch_range
from services.trend_radar.models import jsonable, iso_utc

OLD_TREND_ID = "s3b-replay-trend-nvidia-20261103-20261110"
OLD_BATTLE_ID = "s3b-replay-battle-btc-chatgpt-20261103-20261110"
DEFAULT_SOURCE_DIR = "var/oracle_live_final"
DEFAULT_DATA_DIR = "var/oracle_s2_5_short"
DEFAULT_FIXTURES = "services/oracle/fixtures"
DEFAULT_EVIDENCE_DIR = "docs/evidence"
DEFAULT_S3A = "docs/evidence/s3a_live_scan_20261112.json"


def parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_old_rule(store: OracleStore, market_id: str) -> dict:
    record = store.get_rule_by_market(market_id)
    if not record:
        raise SystemExit(f"old rule not found for {market_id}")
    if record["status"] != "DRAFT":
        raise SystemExit(
            f"old rule {market_id} is {record['status']}, expected DRAFT; refusing to modify it"
        )
    return record


def calibration_for(store: OracleStore, rule: dict) -> dict:
    digest = rule.get("calibration", {}).get("report_digest")
    if not digest:
        raise SystemExit("old rule has no calibration report digest")
    record = store.get_calibration(digest)
    if not record:
        raise SystemExit(f"calibration report not found: {digest}")
    return record["calibration"]


def build_short_rule(
    *,
    old_rule: dict,
    candidate: dict,
    candidate_b: dict | None,
    calibration: dict,
    market_id: str,
    timing: dict,
) -> dict:
    if old_rule["mode"] == "trend_trading":
        return build_trend_rule(
            candidate=candidate,
            baseline_date=date.fromisoformat(old_rule["observation"]["baseline_date"]),
            target_date=date.fromisoformat(old_rule["observation"]["target_date"]),
            threshold_bps=old_rule["formula"]["threshold_bps"],
            min_baseline_views=old_rule["minimum_baseline_views"],
            timing=timing,
            calibration_report=calibration,
            contract=old_rule["contract"],
            replay=True,
            question=old_rule["question"],
            proposal_refs=old_rule["candidate"]["source_proposal_refs"],
            review={"recommendation": old_rule["candidate"]["validation_status"]},
        )
    if candidate_b is None:
        raise SystemExit("battle rule requires two candidates")
    return build_battle_rule(
        candidate_a=candidate,
        candidate_b=candidate_b,
        baseline_date=date.fromisoformat(old_rule["observation"]["baseline_date"]),
        target_date=date.fromisoformat(old_rule["observation"]["target_date"]),
        tie_tolerance_bps=old_rule["formula"]["tie_tolerance_bps"],
        min_baseline_views=old_rule["minimum_baseline_views"],
        timing=timing,
        calibration_report=calibration,
        contract=old_rule["contract"],
        replay=True,
        question=old_rule["question"],
        proposal_refs=old_rule["candidate"]["source_proposal_refs"],
        review={"recommendation": old_rule["candidate"]["validation_status"]},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-data-dir", default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--s3a-evidence", default=DEFAULT_S3A)
    parser.add_argument("--rpc-url", default="https://rpc.testnet.near.org")
    parser.add_argument("--contract-account", default="market.notch-dev.testnet")
    parser.add_argument(
        "--now",
        default=None,
        help="Offline test clock (ISO-8601). Omit to derive from live chain time.",
    )
    parser.add_argument("--entry-minutes", type=int, default=90)
    parser.add_argument("--resolution-delay-minutes", type=int, default=5)
    args = parser.parse_args()

    if args.entry_minutes < 1:
        raise SystemExit("entry-minutes must be positive")
    if args.resolution_delay_minutes < 0:
        raise SystemExit("resolution-delay-minutes must be non-negative")

    source_store = OracleStore(Path(args.source_data_dir) / "oracle.sqlite3")
    try:
        old_trend = load_old_rule(source_store, OLD_TREND_ID)
        old_battle = load_old_rule(source_store, OLD_BATTLE_ID)
        trend_cal = calibration_for(source_store, old_trend["rule"])
        battle_cal = calibration_for(source_store, old_battle["rule"])
        old_evidence = {e["market_id"]: e for e in source_store.list_evidence()}
    finally:
        source_store.close()

    fixed_now = parse_now(args.now)
    if fixed_now is None:
        client = NearRpcClient(
            rpc_url=args.rpc_url, contract_id=args.contract_account
        )
        chain_ns = client.latest_block_timestamp_ns()
        now = datetime.fromtimestamp(chain_ns / 1e9, tz=timezone.utc)
    else:
        now = fixed_now

    open_at = now + timedelta(minutes=2)
    close_at = open_at + timedelta(minutes=args.entry_minutes)
    resolve_after = close_at + timedelta(minutes=args.resolution_delay_minutes)
    timing_base = {"market_timing": market_timing(open_at=open_at, close_at=close_at, resolve_after=resolve_after)}
    stamp = open_at.strftime("%Y%m%dT%H%M%SZ")
    trend_market_id = f"s3b-short-trend-nvidia-{stamp}"
    battle_market_id = f"s3b-short-battle-btc-chatgpt-{stamp}"

    repo = CandidateRepository(args.s3a_evidence)
    nvidia = repo.get_by_title("Nvidia")
    bitcoin = repo.get_by_title("Bitcoin")
    chatgpt = repo.get_by_title("ChatGPT")
    if not (nvidia and bitcoin and chatgpt):
        raise SystemExit("required S3A candidates not found")

    trend_timing = {
        **timing_base,
        "market_id": trend_market_id,
        "baseline_date": date.fromisoformat(old_trend["rule"]["observation"]["baseline_date"]),
        "target_date": date.fromisoformat(old_trend["rule"]["observation"]["target_date"]),
    }
    battle_timing = {
        **timing_base,
        "market_id": battle_market_id,
        "baseline_date": date.fromisoformat(old_battle["rule"]["observation"]["baseline_date"]),
        "target_date": date.fromisoformat(old_battle["rule"]["observation"]["target_date"]),
    }

    new_trend = build_short_rule(
        old_rule=old_trend["rule"],
        candidate=nvidia,
        candidate_b=None,
        calibration=trend_cal,
        market_id=trend_market_id,
        timing=trend_timing,
    )
    new_battle = build_short_rule(
        old_rule=old_battle["rule"],
        candidate=bitcoin,
        candidate_b=chatgpt,
        calibration=battle_cal,
        market_id=battle_market_id,
        timing=battle_timing,
    )

    for name, rule in [("trend", new_trend), ("battle", new_battle)]:
        errors = validate_rule(rule, now=now)
        if errors:
            raise SystemExit(f"{name} rule invalid: {', '.join(errors)}")
        create_args = build_contract_args(rule)
        errors = validate_create_args(create_args)
        if errors:
            raise SystemExit(f"{name} create args invalid: {', '.join(errors)}")
        if int(rule["market_timing"]["close_at_ns"]) <= int(now.timestamp()) * 1_000_000_000:
            raise SystemExit(f"{name} entry close is not in the future")

    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    short_store = OracleStore(Path(args.data_dir) / "oracle.sqlite3")
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        short_store.save_calibration(trend_cal, now=now)
        short_store.save_calibration(battle_cal, now=now)
        trend_record = short_store.freeze_rule(new_trend, now=now)
        battle_record = short_store.freeze_rule(new_battle, now=now)

        fetcher = OracleFixtureFetcher(args.fixtures, now_fn=lambda: now)
        baseline = date.fromisoformat(new_trend["observation"]["baseline_date"])
        target = date.fromisoformat(new_trend["observation"]["target_date"])
        ranges = {
            article: fetch_range(
                fetcher,
                article=article,
                start_date=baseline - timedelta(days=7),
                end_date=target,
            )
            for article in ("Bitcoin", "ChatGPT", "Nvidia")
        }
        for article, result in ranges.items():
            if result.error or result.missing_dates:
                raise SystemExit(
                    f"source range incomplete for {article}: {result.error or result.missing_dates}"
                )

        trend_evidence = build_evidence(new_trend, ranges)
        battle_evidence = build_evidence(new_battle, ranges)
        for label, evidence in [
            ("trend", trend_evidence),
            ("battle", battle_evidence),
        ]:
            check = verify_evidence(
                evidence_to_dict(evidence),
                expected_rule_hash=rule_digest(
                    new_trend if label == "trend" else new_battle
                ),
            )
            if not check["valid"]:
                raise SystemExit(f"{label} evidence invalid: {check['reasons']}")
            if evidence.outcome == "INVALID":
                raise SystemExit(
                    f"{label} evidence is INVALID: {evidence.invalidity_reason}"
                )
            short_store.save_evidence(evidence, now=now)

        trend_args = build_contract_args(new_trend)
        battle_args = build_contract_args(new_battle)
        (evidence_dir / "s2_5_short_create_args_trend_nvidia.json").write_text(
            json.dumps(trend_args, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "s2_5_short_create_args_battle_bitcoin_chatgpt.json").write_text(
            json.dumps(battle_args, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "s2_5_short_evidence_trend_nvidia.json").write_text(
            json.dumps(evidence_to_dict(trend_evidence), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "s2_5_short_evidence_battle_bitcoin_chatgpt.json").write_text(
            json.dumps(evidence_to_dict(battle_evidence), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        summary = {
            "schema_version": "notch.s2_5.short-window-preparation/1",
            "prepared_at_utc": iso_utc(now),
            "chain_time_source": "fixed --now" if fixed_now else "live NEAR testnet block",
            "entry_minutes": args.entry_minutes,
            "resolution_delay_minutes": args.resolution_delay_minutes,
            "previous_timing": {
                "trend": {
                    "market_id": OLD_TREND_ID,
                    "rule_hash": old_trend["rule_hash"],
                    "timing": old_trend["rule"]["market_timing"],
                    "evidence_digest": old_evidence[OLD_TREND_ID]["evidence_digest"],
                    "evidence_outcome": old_evidence[OLD_TREND_ID]["outcome"],
                },
                "battle": {
                    "market_id": OLD_BATTLE_ID,
                    "rule_hash": old_battle["rule_hash"],
                    "timing": old_battle["rule"]["market_timing"],
                    "evidence_digest": old_evidence[OLD_BATTLE_ID]["evidence_digest"],
                    "evidence_outcome": old_evidence[OLD_BATTLE_ID]["outcome"],
                },
            },
            "new_markets": [
                {
                    "name": "trend_nvidia",
                    "market_id": trend_market_id,
                    "mode": "trend_trading",
                    "rule_hash": trend_record["rule_hash"],
                    "status": trend_record["status"],
                    "timing": new_trend["market_timing"],
                    "observation": new_trend["observation"],
                    "formula": new_trend["formula"],
                    "evidence_digest": trend_evidence.evidence_digest,
                    "evidence_outcome": trend_evidence.outcome,
                    "evidence_verification": verify_evidence(
                        evidence_to_dict(trend_evidence),
                        expected_rule_hash=trend_record["rule_hash"],
                    ),
                    "create_args": trend_args,
                },
                {
                    "name": "battle_bitcoin_chatgpt",
                    "market_id": battle_market_id,
                    "mode": "trend_battle",
                    "rule_hash": battle_record["rule_hash"],
                    "status": battle_record["status"],
                    "timing": new_battle["market_timing"],
                    "observation": new_battle["observation"],
                    "formula": new_battle["formula"],
                    "evidence_digest": battle_evidence.evidence_digest,
                    "evidence_outcome": battle_evidence.outcome,
                    "evidence_verification": verify_evidence(
                        evidence_to_dict(battle_evidence),
                        expected_rule_hash=battle_record["rule_hash"],
                    ),
                    "create_args": battle_args,
                },
            ],
            "old_rules_preserved_in": str(Path(args.source_data_dir) / "oracle.sqlite3"),
            "new_rules_store": str(Path(args.data_dir) / "oracle.sqlite3"),
            "source_ranges": {
                article: {
                    "start": result.start_date,
                    "end": result.end_date,
                    "observations": len(result.observations),
                    "missing_dates": result.missing_dates,
                    "raw_response_hash": result.raw_response_hash,
                }
                for article, result in ranges.items()
            },
            "notes": [
                "No transaction was signed or sent by this script.",
                "New rules are DRAFT and require explicit operator approval.",
                "Old S3B rules and evidence are preserved in the source store.",
                "If approval arrives after the entry close, rerun with a fresh chain time.",
            ],
        }
        (evidence_dir / "s2_5_short_preparation.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        short_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
