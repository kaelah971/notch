"""Command-line interface for the Notch Trend Radar (backend only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .http import make_fetcher
from .models import Decision, now_utc
from .service import ScanConfig, ScanInProgress, TrendRadarService
from .store import RadarStore


def _safe_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _health_summary(health: list[dict[str, Any]]) -> str:
    lines = []
    for item in health:
        flags = []
        if item.get("cache_used"):
            flags.append("cache")
        if item.get("stale"):
            flags.append("stale")
        if item.get("rate_limited"):
            flags.append("rate-limited")
        suffix = f" [{','.join(flags)}]" if flags else ""
        lines.append(
            f"- {item['source']}: {item['status']}{suffix}, items={item['item_count']}, "
            f"last_success={item.get('last_success_at')}"
        )
        if item.get("error"):
            lines.append(f"    error: {item['error']}")
    return "\n".join(lines) if lines else "- no source health recorded"


def _scan_summary(result: dict[str, Any]) -> str:
    candidates = result.get("candidates", [])
    proposals = result.get("proposals", [])
    lines = [
        f"scan {result['scan_id']} ({result['scan_kind']}) at {result['completed_at']}",
        f"scan date: {result['scan_date']}  candidates: {len(candidates)}  "
        f"proposed drafts: {len(proposals)}  deduplicated: {result.get('deduplicated', False)}",
        "",
        "source health:",
        _health_summary(result.get("source_health", [])),
        "",
        "top candidates:",
    ]
    for index, candidate in enumerate(candidates[:15], start=1):
        signals = candidate.get("discovery_signals", {})
        reasons = ",".join(candidate.get("eligibility_reasons", []))
        lines.append(
            f"{index:>2}. [{candidate.get('eligibility_status')}] "
            f"{candidate.get('title')} ({candidate.get('category')}) "
            f"score={signals.get('score')} sources={','.join(signals.get('sources', []))} "
            f"id={candidate.get('candidate_id')} reasons={reasons}"
        )
    if not candidates:
        lines.append("(no candidates)")
    lines.append("")
    lines.append("proposed drafts:")
    for proposal in proposals[:15]:
        lines.append(
            f"- [{proposal.get('status')}] {proposal.get('mode')} "
            f"{proposal.get('proposal_id')} :: {proposal.get('topic')}"
        )
    if not proposals:
        lines.append("(no proposals)")
    if result.get("errors"):
        lines.append("")
        lines.append("errors:")
        for error in result["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)


def _candidate_summary(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "(no candidates)"
    lines = []
    for index, candidate in enumerate(candidates, start=1):
        signals = candidate.get("discovery_signals", {})
        lines.append(
            f"{index:>2}. [{candidate.get('eligibility_status')}] {candidate.get('title')} "
            f"({candidate.get('category')}) score={signals.get('score')} "
            f"id={candidate.get('candidate_id')} sources={','.join(signals.get('sources', []))}"
        )
    return "\n".join(lines)


def _proposal_summary(proposals: list[dict[str, Any]]) -> str:
    if not proposals:
        return "(no proposals)"
    lines = []
    for item in proposals:
        proposal = item.get("proposal", item)
        lines.append(
            f"- [{proposal.get('status')}] {proposal.get('mode')} "
            f"{proposal.get('proposal_id')} :: {proposal.get('topic')}"
        )
        if proposal.get("decision_reason"):
            lines.append(
                f"    decision: {proposal.get('status')} by {proposal.get('decided_by')}: "
                f"{proposal.get('decision_reason')}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _safe_stdout()
    parser = argparse.ArgumentParser(
        prog="notch-trend-radar",
        description="Notch Trend Radar — discovery only; never creates markets.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("RADAR_DATA_DIR", "var/trend_radar"),
        help="Durable data/cache directory (default: RADAR_DATA_DIR or var/trend_radar)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run one bounded discovery scan")
    scan.add_argument(
        "--fixtures",
        default=None,
        help="Offline fixture directory (uses recorded responses instead of live APIs)",
    )
    scan.add_argument("--force", action="store_true", help="Bypass recent-scan deduplication")
    scan.add_argument("--summary", action="store_true", help="Human summary instead of JSON")
    scan.add_argument("--output", default=None, help="Optional path for the full scan JSON")

    candidates = sub.add_parser("candidates", help="List discovered candidates")
    candidates.add_argument("--category", default=None)
    candidates.add_argument("--eligibility", default=None)
    candidates.add_argument("--limit", type=int, default=50)
    candidates.add_argument("--summary", action="store_true")

    show = sub.add_parser("show", help="Show one candidate with evidence")
    show.add_argument("candidate_id")

    proposals = sub.add_parser("proposals", help="List market proposal drafts")
    proposals.add_argument(
        "--status", choices=["PROPOSED", "APPROVED", "REJECTED"], default=None
    )
    proposals.add_argument("--limit", type=int, default=100)
    proposals.add_argument("--summary", action="store_true")

    review = sub.add_parser("review", help="Approve or reject a proposal draft")
    review.add_argument("proposal_id")
    decision_group = review.add_mutually_exclusive_group(required=True)
    decision_group.add_argument("--approve", action="store_true")
    decision_group.add_argument("--reject", action="store_true")
    review.add_argument("--reason", required=True)
    review.add_argument("--operator", default=None)

    sub.add_parser("health", help="Show last source health")

    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)
    store = RadarStore(data_dir / "radar.sqlite3")
    try:
        if args.command == "scan":
            mode = "fixture" if args.fixtures else "live"
            fetcher = make_fetcher(
                mode,
                data_dir=data_dir,
                fixtures_dir=args.fixtures,
            )
            service = TrendRadarService(
                fetcher=fetcher,
                store=store,
                config=ScanConfig(),
                operator=os.environ.get("RADAR_OPERATOR", "local-operator"),
            )
            try:
                result = service.scan(force=args.force)
            except ScanInProgress as exc:
                print(str(exc), file=sys.stderr)
                return 2
            output_path = Path(args.output) if args.output else data_dir / "last_scan.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if args.summary:
                print(_scan_summary(result))
            else:
                _print_json(result)
            return 0

        if args.command == "candidates":
            items = service_list(store, args.category, args.eligibility, args.limit)
            if args.summary:
                print(_candidate_summary(items))
            else:
                _print_json(items)
            return 0

        if args.command == "show":
            item = store.get_candidate(args.candidate_id)
            if not item:
                print(f"unknown candidate: {args.candidate_id}", file=sys.stderr)
                return 1
            _print_json(item)
            return 0

        if args.command == "proposals":
            items = store.list_proposals(status=args.status, limit=args.limit)
            if args.summary:
                print(_proposal_summary(items))
            else:
                _print_json(items)
            return 0

        if args.command == "review":
            decision = Decision.APPROVE if args.approve else Decision.REJECT
            operator = (
                args.operator
                or os.environ.get("RADAR_OPERATOR")
                or "local-operator"
            )
            try:
                updated = store.review_proposal(
                    args.proposal_id,
                    decision,
                    args.reason,
                    operator,
                    now_utc(),
                )
            except KeyError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            _print_json(updated)
            return 0

        if args.command == "health":
            _print_json(store.source_health())
            return 0

        parser.print_help()
        return 1
    finally:
        store.close()


def service_list(
    store: RadarStore,
    category: str | None,
    eligibility: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    return store.list_candidates(
        category=category, eligibility=eligibility, limit=limit
    )


if __name__ == "__main__":
    raise SystemExit(main())
