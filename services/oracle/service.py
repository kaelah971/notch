"""Oracle orchestration: calibration, frozen rules, evidence and demo preparation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from services.trend_radar.models import iso_utc, jsonable, now_utc

from .calibration import (
    CALIBRATION_DAYS,
    MIN_BASELINE_VIEWS,
    calibrate_battle,
    calibrate_trend,
)
from .contract import DEFAULT_CONTRACT, NearRpcClient, prepare_resolution
from .evidence import build_evidence, evidence_to_dict, save_evidence, verify_evidence
from .review import CandidateRepository, review_battle_pair, review_candidate
from .rules import (
    build_battle_rule,
    build_contract_args,
    build_trend_rule,
    default_future_timing,
    replay_timing,
    rule_digest,
    validate_rule,
)
from .store import OracleStore
from .wikimedia import fetch_range

DEFAULT_S3A_EVIDENCE = "docs/evidence/s3a_live_scan_20261112.json"
DEFAULT_DATA_DIR = "var/oracle"
DEFAULT_COLLATERAL = "usdc.tidepool-sandbox.testnet"


class OracleDataError(RuntimeError):
    pass


@dataclass
class OracleConfig:
    data_dir: str = DEFAULT_DATA_DIR
    s3a_evidence_path: str = DEFAULT_S3A_EVIDENCE
    contract_account: str = DEFAULT_CONTRACT
    collateral_token: str = DEFAULT_COLLATERAL
    min_baseline_views: int = MIN_BASELINE_VIEWS
    calibration_days: int = CALIBRATION_DAYS
    calibration_end: str | None = None
    live: bool = False


class OracleService:
    def __init__(
        self,
        *,
        fetcher: Any,
        store: OracleStore,
        config: OracleConfig,
        now_fn: Callable[[], datetime] = now_utc,
    ) -> None:
        self.fetcher = fetcher
        self.store = store
        self.config = config
        self.now_fn = now_fn
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.repo = CandidateRepository(config.s3a_evidence_path)

    # ------------------------------------------------------------------
    # Source data
    # ------------------------------------------------------------------
    def calibration_end(self) -> date:
        if self.config.calibration_end:
            return date.fromisoformat(self.config.calibration_end)
        data = json.loads(
            Path(self.config.s3a_evidence_path).read_text(encoding="utf-8")
        )
        reporting = (
            data.get("source_context", {}).get("wikimedia", {}).get("reporting_date")
        )
        if reporting:
            return date.fromisoformat(reporting)
        return self.now_fn().date() - timedelta(days=1)

    def load_ranges(
        self, articles: list[str], start: date, end: date
    ) -> dict[str, Any]:
        ranges = {}
        for article in articles:
            ranges[article] = fetch_range(
                self.fetcher, article=article, start_date=start, end_date=end
            )
        return ranges

    def _require_ranges(self, ranges: dict[str, Any]) -> None:
        errors = [
            f"{article}: {result.error}"
            for article, result in ranges.items()
            if result.error
        ]
        if errors:
            raise OracleDataError("; ".join(errors))

    # ------------------------------------------------------------------
    # Demo shortlist
    # ------------------------------------------------------------------
    def demo(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or self.now_fn()
        calibration_end = self.calibration_end()
        replay_baseline = date(2026, 11, 3)
        replay_target = date(2026, 11, 10)
        replay_cal_end = replay_baseline - timedelta(days=1)
        range_start = min(calibration_end, replay_cal_end) - timedelta(
            days=self.config.calibration_days + 6
        )
        range_end = max(calibration_end, replay_target)
        articles = ["Bitcoin", "ChatGPT", "Nvidia"]
        ranges = self.load_ranges(articles, range_start, range_end)
        self._require_ranges(ranges)

        btc = self.repo.get_by_title("Bitcoin")
        cg = self.repo.get_by_title("ChatGPT")
        nv = self.repo.get_by_title("Nvidia")
        if not (btc and cg and nv):
            raise OracleDataError(
                "S3A candidates Bitcoin, ChatGPT and Nvidia are required"
            )

        btc_replay_cal = calibrate_trend(
            ranges["Bitcoin"],
            baseline_date=replay_baseline,
            target_date=replay_target,
            calibration_end=replay_cal_end,
            replay=True,
            min_baseline_views=self.config.min_baseline_views,
        )
        nv_replay_cal = calibrate_trend(
            ranges["Nvidia"],
            baseline_date=replay_baseline,
            target_date=replay_target,
            calibration_end=replay_cal_end,
            replay=True,
            min_baseline_views=self.config.min_baseline_views,
        )
        cg_replay_cal = calibrate_trend(
            ranges["ChatGPT"],
            baseline_date=replay_baseline,
            target_date=replay_target,
            calibration_end=replay_cal_end,
            replay=True,
            min_baseline_views=self.config.min_baseline_views,
        )
        battle_cal = calibrate_battle(
            ranges["Bitcoin"],
            ranges["ChatGPT"],
            baseline_date=replay_baseline,
            target_date=replay_target,
            calibration_end=replay_cal_end,
            replay=True,
            min_baseline_views=self.config.min_baseline_views,
        )
        future_timing = default_future_timing(now)
        future_baseline = future_timing["baseline_date"]
        future_target = future_timing["target_date"]
        future_cal = calibrate_trend(
            ranges["Bitcoin"],
            baseline_date=future_baseline,
            target_date=future_target,
            calibration_end=calibration_end,
            replay=False,
            min_baseline_views=self.config.min_baseline_views,
        )
        for label, report in [
            ("future", future_cal),
            ("bitcoin replay", btc_replay_cal),
            ("nvidia replay", nv_replay_cal),
            ("chatgpt replay", cg_replay_cal),
            ("battle", battle_cal),
        ]:
            if report.status != "OK":
                raise OracleDataError(
                    f"{label} calibration failed: {', '.join(report.reasons)}"
                )

        calibration_reports = {
            "future_bitcoin": future_cal,
            "replay_trend_bitcoin": btc_replay_cal,
            "replay_trend_nvidia": nv_replay_cal,
            "replay_trend_chatgpt": cg_replay_cal,
            "replay_battle_bitcoin_chatgpt": battle_cal,
        }
        calibration_summaries = []
        calibration_dir = self.data_dir / "calibrations"
        calibration_dir.mkdir(parents=True, exist_ok=True)
        for name, report in calibration_reports.items():
            self.store.save_calibration(report, now=now)
            payload = jsonable(report)
            digest = report.report_digest
            path = calibration_dir / f"{digest.split(':', 1)[1]}.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            calibration_summaries.append(
                {
                    "name": name,
                    "report_digest": digest,
                    "article": report.article,
                    "topic_b_article": report.topic_b_article,
                    "mode": report.mode,
                    "status": report.status,
                    "observation_status": report.observation_status,
                    "calibration_start": report.calibration_start,
                    "calibration_end": report.calibration_end,
                    "suggested_threshold_bps": report.suggested_threshold_bps,
                    "suggested_tie_tolerance_bps": report.suggested_tie_tolerance_bps,
                    "path": str(path),
                }
            )

        contract = {
            "network": "testnet",
            "account": self.config.contract_account,
            "collateral_token": self.config.collateral_token,
        }
        btc_review = review_candidate(btc, calibration=btc_replay_cal)
        cg_review = review_candidate(cg, calibration=cg_replay_cal)
        nv_review = review_candidate(nv, calibration=nv_replay_cal)
        future_review = review_candidate(btc, calibration=future_cal)
        battle_review = review_battle_pair(btc, cg, calibration=battle_cal)
        correlation_example = review_battle_pair(
            nv,
            self.repo.get_by_title("Jensen Huang"),
            calibration=nv_replay_cal,
        )
        proposal_refs = self._proposal_refs(btc, cg, nv)

        future_timing["market_id"] = (
            f"s3b-future-btc-{future_baseline.strftime('%Y%m%d')}-"
            f"{future_target.strftime('%Y%m%d')}"
        )
        future_rule = build_trend_rule(
            candidate=btc,
            baseline_date=future_baseline,
            target_date=future_target,
            threshold_bps=future_cal.suggested_threshold_bps,
            min_baseline_views=self.config.min_baseline_views,
            timing=future_timing,
            calibration_report=jsonable(future_cal),
            contract=contract,
            replay=False,
            question=(
                "FORECAST (not a replay): Will daily en.wikipedia.org pageviews for "
                f"Bitcoin grow by at least {future_cal.suggested_threshold_bps / 100:.2f}% "
                f"on the full UTC day {future_target.isoformat()} versus the full UTC "
                f"day {future_baseline.isoformat()}? (Wikimedia Pageviews, all-access, user)"
            ),
            proposal_refs=proposal_refs["bitcoin_trend"],
            review=jsonable(future_review),
        )

        trend_timing = replay_timing(
            now, baseline_date=replay_baseline, target_date=replay_target
        )
        trend_timing["market_id"] = (
            f"s3b-replay-trend-nvidia-{replay_baseline.strftime('%Y%m%d')}-"
            f"{replay_target.strftime('%Y%m%d')}"
        )
        trend_rule = build_trend_rule(
            candidate=nv,
            baseline_date=replay_baseline,
            target_date=replay_target,
            threshold_bps=nv_replay_cal.suggested_threshold_bps,
            min_baseline_views=self.config.min_baseline_views,
            timing=trend_timing,
            calibration_report=jsonable(nv_replay_cal),
            contract=contract,
            replay=True,
            question=(
                "HISTORICAL REPLAY (not a forecast): Will daily en.wikipedia.org "
                f"pageviews for Nvidia grow by at least "
                f"{nv_replay_cal.suggested_threshold_bps / 100:.2f}% on the full UTC "
                f"day {replay_target.isoformat()} versus the full UTC day "
                f"{replay_baseline.isoformat()}? (Wikimedia Pageviews, all-access, user)"
            ),
            proposal_refs=proposal_refs["nvidia_trend"],
            review=jsonable(nv_review),
        )

        battle_timing = replay_timing(
            now, baseline_date=replay_baseline, target_date=replay_target
        )
        battle_timing["market_id"] = (
            f"s3b-replay-battle-btc-chatgpt-"
            f"{replay_baseline.strftime('%Y%m%d')}-{replay_target.strftime('%Y%m%d')}"
        )
        battle_rule = build_battle_rule(
            candidate_a=btc,
            candidate_b=cg,
            baseline_date=replay_baseline,
            target_date=replay_target,
            tie_tolerance_bps=battle_cal.suggested_tie_tolerance_bps,
            min_baseline_views=self.config.min_baseline_views,
            timing=battle_timing,
            calibration_report=jsonable(battle_cal),
            contract=contract,
            replay=True,
            question=(
                "HISTORICAL REPLAY (not a forecast): Which topic had higher "
                f"normalized Wikimedia pageview growth from the full UTC day "
                f"{replay_baseline.isoformat()} to the full UTC day "
                f"{replay_target.isoformat()}: Bitcoin or ChatGPT? A difference "
                f"within {battle_cal.suggested_tie_tolerance_bps} bps is a tie and "
                "voids the market."
            ),
            proposal_refs=proposal_refs["battle"],
            review=jsonable(battle_review),
        )

        frozen = {}
        for name, rule in [
            ("future_bitcoin", future_rule),
            ("replay_trend_nvidia", trend_rule),
            ("replay_battle_bitcoin_chatgpt", battle_rule),
        ]:
            errors = validate_rule(rule, now=now)
            if errors:
                raise OracleDataError(f"{name} rule invalid: {', '.join(errors)}")
            frozen[name] = self.store.freeze_rule(rule, now=now)

        evidence_items = {}
        for name, rule in [
            ("replay_trend_nvidia", trend_rule),
            ("replay_battle_bitcoin_chatgpt", battle_rule),
        ]:
            evidence = build_evidence(rule, ranges)
            evidence_doc = evidence_to_dict(evidence)
            verification = verify_evidence(
                evidence_doc, expected_rule_hash=rule_digest(rule)
            )
            if not verification["valid"]:
                raise OracleDataError(
                    f"{name} evidence invalid: {', '.join(verification['reasons'])}"
                )
            self.store.save_evidence(evidence, now=now)
            path = save_evidence(evidence, self.data_dir / "evidence")
            if evidence.outcome == "INVALID":
                raise OracleDataError(
                    f"{name} evidence is INVALID: {evidence.invalidity_reason}"
                )
            evidence_items[name] = {
                "evidence": evidence_doc,
                "verification": verification,
                "path": str(path),
            }

        for review in [
            btc_review,
            cg_review,
            nv_review,
            future_review,
            battle_review,
            correlation_example,
        ]:
            self.store.save_review(review, now=now)

        rules = []
        for name, frozen_rule in frozen.items():
            rule = frozen_rule["rule"]
            record = {
                "name": name,
                "rule_hash": frozen_rule["rule_hash"],
                "status": frozen_rule["status"],
                "rule": rule,
                "contract_args": build_contract_args(rule),
                "evidence": evidence_items.get(name),
                "evidence_pending": name not in evidence_items,
                "resolution_plan_preview": None,
            }
            if name in evidence_items:
                record["resolution_plan_preview"] = jsonable(
                    prepare_resolution(
                        frozen_rule,
                        evidence_items[name]["evidence"],
                        market=None,
                        contract_account=self.config.contract_account,
                        now=now,
                    )
                )
            rules.append(record)

        demo = {
            "schema_version": "notch.oracle.demo/1",
            "generated_at": iso_utc(now),
            "onchain_actions": "none",
            "calibration_end": calibration_end.isoformat(),
            "replay_observation": {
                "baseline_date": replay_baseline.isoformat(),
                "target_date": replay_target.isoformat(),
            },
            "future_observation": {
                "baseline_date": future_baseline.isoformat(),
                "target_date": future_target.isoformat(),
            },
            "calibrations": calibration_summaries,
            "source_ranges": {
                article: {
                    "start": result.start_date,
                    "end": result.end_date,
                    "observations": len(result.observations),
                    "missing_dates": result.missing_dates,
                    "retrieved_at": iso_utc(result.retrieved_at)
                    if result.retrieved_at
                    else None,
                    "raw_response_hash": result.raw_response_hash,
                    "source_url": result.source_url,
                }
                for article, result in ranges.items()
            },
            "reviews": [
                jsonable(btc_review),
                jsonable(cg_review),
                jsonable(nv_review),
                jsonable(future_review),
                jsonable(battle_review),
            ],
            "correlation_example": jsonable(correlation_example),
            "rules": rules,
            "battle_pair": {
                "topic_a": "Bitcoin",
                "topic_b": "ChatGPT",
                "recommendation": battle_review.recommendation,
                "review": jsonable(battle_review),
            },
            "notes": [
                "All rules are DRAFT and require explicit operator approval.",
                "No market is created, signed or resolved by this demo.",
                "Replay markets use historical observations with future entry/close timestamps and are explicitly labeled.",
                "The future market has no evidence until its observation window passes.",
                "Evidence hashes prove integrity, not organic attention.",
            ],
        }
        output = self.data_dir / "demo.json"
        output.write_text(
            json.dumps(demo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return demo

    def _proposal_refs(self, btc, cg, nv) -> dict[str, list[str]]:
        data = json.loads(
            Path(self.config.s3a_evidence_path).read_text(encoding="utf-8")
        )
        proposals = data.get("proposals", [])

        def refs_for(candidate: dict, mode: str | None = None) -> list[str]:
            candidate_id = candidate["candidate_id"]
            return [
                proposal["proposal_id"]
                for proposal in proposals
                if candidate_id in proposal.get("candidate_ids", [])
                and (mode is None or proposal.get("mode") == mode)
            ]

        return {
            "bitcoin_trend": refs_for(btc, "trend_trading"),
            "nvidia_trend": refs_for(nv, "trend_trading"),
            "battle": refs_for(btc, "trend_battle")
            + refs_for(cg, "trend_battle"),
        }

    # ------------------------------------------------------------------
    # Resolution preparation
    # ------------------------------------------------------------------
    def resolve_rule(
        self, rule_hash: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        now = now or self.now_fn()
        rule_record = self.store.get_rule(rule_hash)
        if not rule_record:
            raise KeyError(f"unknown rule: {rule_hash}")
        rule = rule_record["rule"]
        baseline = date.fromisoformat(rule["observation"]["baseline_date"])
        target = date.fromisoformat(rule["observation"]["target_date"])
        if now.date() <= target:
            return {
                "status": "PENDING_OBSERVATION",
                "market_id": rule["market_id"],
                "rule_hash": rule_hash,
                "target_date": target.isoformat(),
                "message": "Target observation day is not complete yet.",
            }
        articles = [topic["article_title"] for topic in rule["topics"]]
        ranges = self.load_ranges(articles, baseline - timedelta(days=7), target)
        self._require_ranges(ranges)
        evidence = build_evidence(rule, ranges)
        evidence_doc = evidence_to_dict(evidence)
        verification = verify_evidence(evidence_doc, expected_rule_hash=rule_hash)
        if not verification["valid"]:
            raise OracleDataError(
                "evidence invalid: " + ", ".join(verification["reasons"])
            )
        self.store.save_evidence(evidence, now=now)
        path = save_evidence(evidence, self.data_dir / "evidence")
        return {
            "status": "EVIDENCE_READY",
            "market_id": rule["market_id"],
            "rule_hash": rule_hash,
            "outcome": evidence.outcome,
            "evidence_digest": evidence.evidence_digest,
            "evidence": evidence_doc,
            "verification": verification,
            "path": str(path),
        }

    def prepare(
        self,
        *,
        rule_hash: str,
        evidence_digest: str,
        onchain: bool = False,
        market_view: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or self.now_fn()
        rule_record = self.store.get_rule(rule_hash)
        if not rule_record:
            raise KeyError(f"unknown rule: {rule_hash}")
        evidence_record = self.store.get_evidence(evidence_digest)
        if not evidence_record:
            raise KeyError(f"unknown evidence: {evidence_digest}")
        evidence = evidence_record["evidence"]
        contract_config = None
        if onchain:
            reader = NearRpcClient(contract_id=self.config.contract_account)
            market_view = reader.get_market(rule_record["rule"]["market_id"])
            contract_config = reader.get_contract_config()
            now_ns = reader.latest_block_timestamp_ns()
        else:
            now_ns = int(now.timestamp()) * 1_000_000_000
        plan = prepare_resolution(
            rule_record,
            evidence,
            market=market_view,
            contract_config=contract_config,
            contract_account=self.config.contract_account,
            now=now,
            now_ns=now_ns,
        )
        if plan.status not in {"PREPARED", "ALREADY_FINAL"}:
            return {
                "job_id": plan.job_id,
                "idempotent": False,
                "persisted": False,
                "plan": jsonable(plan),
            }
        job = self.store.prepare_job(plan, now=now)
        job["persisted"] = True
        return job

    def approve_rule(
        self,
        rule_hash: str,
        *,
        operator: str,
        reason: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.store.approve_rule(
            rule_hash, operator=operator, reason=reason, now=now or self.now_fn()
        )
