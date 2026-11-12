"""Command-line interface for the deterministic attention oracle (S3B)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.trend_radar.http import FixtureFetcher, make_fetcher
from services.trend_radar.models import iso_utc, jsonable, now_utc

from .calibration import CALIBRATION_DAYS, calibrate_battle, calibrate_trend
from .contract import NearRpcClient
from .evidence import verify_evidence
from .fixture_fetcher import OracleFixtureFetcher
from .service import DEFAULT_S3A_EVIDENCE, OracleConfig, OracleService
from .store import OracleStore


def _stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _parse_day(value: str) -> date:
    return date.fromisoformat(value)


def _parse_now(value: str | None) -> datetime:
    if not value:
        return now_utc()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_service(args: argparse.Namespace, *, now: datetime) -> tuple[OracleService, OracleStore, Any]:
    mode = "fixture" if args.fixtures else "live"
    if mode == "fixture":
        fetcher = OracleFixtureFetcher(args.fixtures, now_fn=lambda: now)
    else:
        # The market-timing clock may be fixed for deterministic demo rules,
        # while a live source retrieval records its real wall-clock timestamp.
        fetcher = make_fetcher(
            "live",
            data_dir=args.data_dir,
            now_fn=now_utc,
        )
    store = OracleStore(Path(args.data_dir) / "oracle.sqlite3")
    config = OracleConfig(
        data_dir=args.data_dir,
        s3a_evidence_path=args.s3a_evidence,
        calibration_end=args.calibration_end,
        live=mode == "live",
    )
    return (
        OracleService(fetcher=fetcher, store=store, config=config, now_fn=lambda: now),
        store,
        fetcher,
    )


def _demo_summary(demo: dict[str, Any]) -> str:
    lines = [
        f"demo at {demo['generated_at']}  onchain_actions={demo['onchain_actions']}",
        f"calibration end: {demo['calibration_end']}",
        f"future observation: {demo['future_observation']}",
        f"replay observation: {demo['replay_observation']}",
        "",
        "rules:",
    ]
    for item in demo["rules"]:
        rule = item["rule"]
        lines.append(
            f"- {item['name']}: {rule['market_id']} [{item['status']}] "
            f"hash={item['rule_hash']}"
        )
        if item["evidence"]:
            ev = item["evidence"]["evidence"]
            lines.append(
                f"    evidence={ev['evidence_digest']} outcome={ev['outcome']} "
                f"verified={item['evidence']['verification']['valid']}"
            )
        else:
            lines.append("    evidence: pending observation window")
        plan = item.get("resolution_plan_preview")
        if plan:
            lines.append(
                f"    resolution preview: {plan['status']} {plan['action']} "
                f"blockers={plan['blockers']}"
            )
    lines.extend(["", "reviews:"])
    for review in demo["reviews"]:
        lines.append(
            f"- {review['title']}: {review['recommendation']} "
            f"measurement={review['measurement_status']} "
            f"interest={review['market_interest']}"
        )
    lines.append("")
    lines.append(
        "battle pair recommendation: " + demo["battle_pair"]["recommendation"]
    )
    lines.append("")
    lines.append("correlation example: " + demo["correlation_example"]["recommendation"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _stdout()
    parser = argparse.ArgumentParser(
        prog="notch-oracle",
        description=(
            "Notch deterministic attention oracle. Computes evidence and "
            "prepares resolution calls; never signs or submits."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("ORACLE_DATA_DIR", "var/oracle"),
        help="Local data/DB directory (default: var/oracle)",
    )
    parser.add_argument(
        "--s3a-evidence",
        default=DEFAULT_S3A_EVIDENCE,
        help="S3A live evidence JSON used for candidate selection",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="Fixed UTC timestamp for deterministic demo/replay (ISO-8601)",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="Offline fixture directory; omit for live Wikimedia access",
    )
    parser.add_argument(
        "--calibration-end",
        default=None,
        help="Latest complete calibration day (YYYY-MM-DD); defaults to S3A reporting date",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Prepare the S3B shortlist and evidence")
    demo.add_argument("--summary", action="store_true")
    demo.add_argument("--output", default=None)

    calibrate = sub.add_parser("calibrate", help="Calibrate a trend or battle")
    calibrate.add_argument("--article", required=True)
    calibrate.add_argument("--battle-article", default=None)
    calibrate.add_argument("--baseline", required=True)
    calibrate.add_argument("--target", required=True)
    calibrate.add_argument("--calibration-end", dest="calibration_end_cli", required=True)
    calibrate.add_argument("--replay", action="store_true")

    rules = sub.add_parser("rules", help="List frozen rules")
    rules.add_argument("--status", default=None)
    rules.add_argument("--summary", action="store_true")

    show_rule = sub.add_parser("show-rule", help="Show a frozen rule")
    show_rule.add_argument("rule_hash")

    approve = sub.add_parser("approve-rule", help="Operator approval (local only)")
    approve.add_argument("rule_hash")
    approve.add_argument("--reason", required=True)
    approve.add_argument("--operator", default=os.environ.get("ORACLE_OPERATOR", "local-operator"))

    evidence_list = sub.add_parser("evidence", help="List stored evidence")
    evidence_list.add_argument("--market-id", default=None)

    verify = sub.add_parser("verify-evidence", help="Recompute and verify an evidence receipt")
    verify.add_argument("path")

    resolve = sub.add_parser("resolve", help="Fetch observations and build evidence for a frozen rule")
    resolve.add_argument("rule_hash")
    resolve.add_argument("--summary", action="store_true")

    prepare = sub.add_parser("prepare-resolution", help="Prepare the exact S2 contract call")
    prepare.add_argument("--rule-hash", required=True)
    prepare.add_argument("--evidence-digest", required=True)
    prepare.add_argument("--onchain", action="store_true", help="Read the deployed S2 market")
    prepare.add_argument("--market-json", default=None, help="Explicit onchain market view JSON")

    jobs = sub.add_parser("jobs", help="List prepared resolution jobs")
    jobs.add_argument("--market-id", default=None)
    jobs.add_argument("--summary", action="store_true")

    show_job = sub.add_parser("show-job", help="Show a resolution job")
    show_job.add_argument("job_id")

    reviews = sub.add_parser("reviews", help="List candidate reviews")
    reviews.add_argument("--summary", action="store_true")

    args = parser.parse_args(argv)
    now = _parse_now(args.now)
    service, store, _fetcher = _build_service(args, now=now)
    try:
        if args.command == "demo":
            demo_data = service.demo(now=now)
            output = Path(args.output) if args.output else Path(args.data_dir) / "demo.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(demo_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if args.summary:
                print(_demo_summary(demo_data))
            else:
                _print_json(demo_data)
            return 0

        if args.command == "calibrate":
            baseline = _parse_day(args.baseline)
            target = _parse_day(args.target)
            cal_end = _parse_day(args.calibration_end_cli)
            start = cal_end - timedelta(days=CALIBRATION_DAYS + 6)
            ranges = service.load_ranges(
                [args.article] + ([args.battle_article] if args.battle_article else []),
                start,
                max(cal_end, target),
            )
            service._require_ranges(ranges)
            if args.battle_article:
                report = calibrate_battle(
                    ranges[args.article],
                    ranges[args.battle_article],
                    baseline_date=baseline,
                    target_date=target,
                    calibration_end=cal_end,
                    replay=args.replay,
                )
            else:
                report = calibrate_trend(
                    ranges[args.article],
                    baseline_date=baseline,
                    target_date=target,
                    calibration_end=cal_end,
                    replay=args.replay,
                )
            _print_json(jsonable(report))
            return 0

        if args.command == "rules":
            items = store.list_rules(status=args.status)
            if args.summary:
                for item in items:
                    print(
                        f"[{item['status']}] {item['rule']['market_id']} "
                        f"{item['rule_hash']} {item['rule']['mode']}"
                    )
            else:
                _print_json(items)
            return 0

        if args.command == "show-rule":
            item = store.get_rule(args.rule_hash)
            if not item:
                print(f"unknown rule: {args.rule_hash}", file=sys.stderr)
                return 1
            _print_json(item)
            return 0

        if args.command == "approve-rule":
            try:
                item = store.approve_rule(
                    args.rule_hash,
                    operator=args.operator,
                    reason=args.reason,
                    now=now,
                )
            except KeyError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            _print_json(item)
            return 0

        if args.command == "evidence":
            _print_json(store.list_evidence(args.market_id))
            return 0

        if args.command == "verify-evidence":
            doc = json.loads(Path(args.path).read_text(encoding="utf-8"))
            result = verify_evidence(doc)
            _print_json(result)
            return 0 if result["valid"] else 1

        if args.command == "resolve":
            try:
                result = service.resolve_rule(args.rule_hash, now=now)
            except KeyError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            except Exception as exc:
                print(f"resolve failed: {exc}", file=sys.stderr)
                return 2
            if args.summary:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                _print_json(result)
            return 0

        if args.command == "prepare-resolution":
            market_view = None
            if args.market_json:
                market_view = json.loads(Path(args.market_json).read_text(encoding="utf-8"))
            try:
                job = service.prepare(
                    rule_hash=args.rule_hash,
                    evidence_digest=args.evidence_digest,
                    onchain=args.onchain,
                    market_view=market_view,
                    now=now,
                )
            except KeyError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            except Exception as exc:
                print(f"prepare failed: {exc}", file=sys.stderr)
                return 2
            _print_json(job)
            return 0

        if args.command == "jobs":
            items = store.list_jobs(market_id=args.market_id)
            if args.summary:
                for item in items:
                    plan = item["plan"]
                    print(
                        f"[{plan['status']}] {plan['market_id']} {plan['action']} "
                        f"{plan['job_id']} evidence={plan['evidence_digest']}"
                    )
            else:
                _print_json(items)
            return 0

        if args.command == "show-job":
            item = store.get_job(args.job_id)
            if not item:
                print(f"unknown job: {args.job_id}", file=sys.stderr)
                return 1
            _print_json(item)
            return 0

        if args.command == "reviews":
            items = store.list_reviews()
            if args.summary:
                for item in items:
                    review = item["review"]
                    print(
                        f"[{review['recommendation']}] {review['title']} "
                        f"measurement={review['measurement_status']} "
                        f"interest={review['market_interest']}"
                    )
            else:
                _print_json(items)
            return 0

        parser.print_help()
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
