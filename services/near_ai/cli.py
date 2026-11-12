"""CLI for S5 NEAR AI trend briefs.

Generation is on demand.  There is no background job that generates a brief for
every Radar candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .client import NearAIClient, NearAIError
from .config import NearAIConfig
from .grounding import GroundingError
from .service import BriefService
from .store import BriefStore
from .validation import BriefValidationError


def _stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _service(args: argparse.Namespace) -> tuple[BriefService, BriefStore]:
    config = NearAIConfig.from_env()
    overrides = {}
    if args.data_dir:
        overrides["data_dir"] = args.data_dir
    if args.radar_db:
        overrides["radar_db"] = args.radar_db
    if args.oracle_db:
        overrides["oracle_db"] = args.oracle_db
    if args.model:
        overrides["model"] = args.model
    if args.base_url:
        overrides["base_url"] = args.base_url
    if overrides:
        config = replace(config, **overrides)
    store = BriefStore(Path(config.data_dir) / "briefs.sqlite3")
    client = NearAIClient(config=config)
    return BriefService(config=config, client=client, store=store), store


def main(argv: list[str] | None = None) -> int:
    _stdout()
    parser = argparse.ArgumentParser(
        prog="notch-near-ai",
        description="S5 evidence-grounded NEAR AI trend briefs. AI never settles markets.",
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--radar-db", default=None)
    parser.add_argument("--oracle-db", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Check key/model catalog without inference")

    models = sub.add_parser("models", help="List live NEAR AI models")
    models.add_argument("--limit", type=int, default=30)

    radar = sub.add_parser("radar-brief", help="Generate or load a Radar brief")
    radar.add_argument("--candidate-id", required=True)
    radar.add_argument("--force", action="store_true")

    market = sub.add_parser("market-brief", help="Generate or load a market brief")
    market.add_argument("--market-id", required=True)
    market.add_argument("--force", action="store_true")

    listing = sub.add_parser("list", help="List cached briefs")
    listing.add_argument("--type", choices=["radar", "market"], default=None)
    listing.add_argument("--candidate-id", default=None)
    listing.add_argument("--market-id", default=None)
    listing.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="Show one cached brief")
    show.add_argument("--brief-id", required=True)

    args = parser.parse_args(argv)
    service: BriefService | None = None
    store: BriefStore | None = None
    try:
        service, store = _service(args)
        if args.command == "status":
            _print_json(service.status())
            return 0
        if args.command == "models":
            models = service.client.list_models()
            models.sort(key=lambda m: (m.price_per_million()[0], m.price_per_million()[1], m.model_id))
            _print_json(
                {
                    "count": len(models),
                    "selected": service.config.model,
                    "models": [m.to_dict() for m in models[: max(1, args.limit)]],
                }
            )
            return 0
        if args.command == "radar-brief":
            _print_json(service.radar_brief(args.candidate_id, force=args.force).to_dict())
            return 0
        if args.command == "market-brief":
            _print_json(service.market_brief(args.market_id, force=args.force).to_dict())
            return 0
        if args.command == "list":
            items = service.list(
                brief_type=args.type,
                candidate_id=args.candidate_id,
                market_id=args.market_id,
                limit=args.limit,
            )
            _print_json([service.brief_summary(item) for item in items])
            return 0
        if args.command == "show":
            brief = service.get(args.brief_id)
            if brief is None:
                print(json.dumps({"error": {"code": "BRIEF_NOT_FOUND", "message": args.brief_id}}), file=sys.stderr)
                return 1
            _print_json(brief.to_dict())
            return 0
        parser.error(f"unknown command: {args.command}")
        return 2
    except (GroundingError, BriefValidationError, NearAIError) as exc:
        payload = exc.as_dict() if hasattr(exc, "as_dict") else {"message": str(exc)}
        print(json.dumps({"error": payload}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
