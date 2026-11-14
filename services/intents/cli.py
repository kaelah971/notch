"""Command-line interface for the S4 Tidepool testnet funding adapter.

No command signs or broadcasts a chain transaction.  ``prepare-swap`` creates a
live quote and prints exact deposit instructions, then stops.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .balance import NearRpcError, make_reader
from .client import RateLimiter, TidepoolClient, TidepoolError
from .config import IntentsConfig
from .models import DepositType
from .service import IntentsFundingService
from .store import FundingStore, FundingStoreError
from .validation import ValidationError


def _stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _build_service(args: argparse.Namespace) -> tuple[IntentsFundingService, FundingStore]:
    config = IntentsConfig.from_env()
    if args.data_dir:
        config = IntentsConfig(
            **{
                **config.__dict__,
                "data_dir": args.data_dir,
            }
        )
    if args.base_url:
        config = IntentsConfig(
            **{
                **config.__dict__,
                "base_url": args.base_url,
            }
        )
    store = FundingStore(Path(config.data_dir) / "funding.sqlite3")
    client = TidepoolClient(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        rate_limiter=RateLimiter(interval_seconds=config.rate_limit_seconds),
    )
    reader = make_reader(config)
    service = IntentsFundingService(
        client=client,
        store=store,
        config=config,
        reader=reader,
    )
    return service, store


def _add_quote_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-asset",
        default=os.environ.get(
            "INTENTS_SOURCE_ASSET", "nep141:usdt.tidepool-sandbox.testnet"
        ),
    )
    parser.add_argument("--amount", required=True, help="integer base units")
    parser.add_argument(
        "--recipient",
        default=os.environ.get("NOTCH_ACCOUNT", "notch-dev.testnet"),
    )
    parser.add_argument("--refund-to", default=None)
    parser.add_argument("--source-chain", default=None, help="live token blockchain, or external")
    parser.add_argument(
        "--deposit-type",
        default=DepositType.INTENTS.value,
        choices=[DepositType.INTENTS.value, DepositType.ORIGIN_CHAIN.value],
    )
    parser.add_argument("--slippage-bps", type=int, default=None)
    parser.add_argument("--deadline-minutes", type=int, default=30)


def main(argv: list[str] | None = None) -> int:
    _stdout()
    parser = argparse.ArgumentParser(
        prog="notch-intents",
        description=(
            "S4 Tidepool testnet funding adapter. Read-only and quote-only; "
            "no chain transaction is signed or broadcast."
        ),
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--base-url", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    tokens = sub.add_parser("tokens", help="List live /v0/tokens")
    tokens.add_argument("--include-ondo", action="store_true")

    sub.add_parser("routes", help="List supported legacy NEAR-testnet routes to USDC")
    sub.add_parser("external-routes", help="List live external-testnet routes to USDC")

    dry = sub.add_parser("dry-quote", help="Request a dry quote (no deposit address)")
    _add_quote_args(dry)

    prepare = sub.add_parser(
        "prepare-swap",
        help="Request a live quote and print deposit instructions; does not transfer",
    )
    _add_quote_args(prepare)

    instructions = sub.add_parser("deposit-instructions", help="Show instructions for a quote")
    instructions.add_argument("--quote-id", required=True)

    record = sub.add_parser("record-deposit", help="Record a deposit tx hash locally")
    record.add_argument("--quote-id", required=True)
    record.add_argument("--tx-hash", required=True)
    record.add_argument(
        "--submit",
        action="store_true",
        help="Notify Tidepool with POST /v0/deposit/submit (does not send funds)",
    )

    status = sub.add_parser("status", help="Poll GET /v0/status and verify balance")
    status.add_argument("--quote-id", required=True)
    status.add_argument("--max-attempts", type=int, default=None)
    status.add_argument("--interval", type=float, default=None)

    observe = sub.add_parser(
        "capture-pre-transfer-balance",
        help="Capture one finalized destination balance before deposit",
    )
    observe.add_argument("--quote-id", required=True)

    verify = sub.add_parser("verify-balance", help="Verify destination USDC increase")
    verify.add_argument("--quote-id", required=True)

    funding = sub.add_parser("funding", help="Read wallet USDC collateral readiness")
    funding.add_argument("--account", default=os.environ.get("NOTCH_ACCOUNT", "notch-dev.testnet"))

    show = sub.add_parser("show", help="Show a persisted funding quote")
    show.add_argument("--quote-id", required=True)

    listing = sub.add_parser("list", help="List persisted funding quotes")
    listing.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)
    service: IntentsFundingService | None = None
    store: FundingStore | None = None
    try:
        service, store = _build_service(args)
        if args.command == "tokens":
            _print_json([token.to_dict() for token in service.discover_tokens(include_ondo=args.include_ondo)])
            return 0
        if args.command == "routes":
            _print_json([route.to_dict() for route in service.supported_routes()])
            return 0
        if args.command == "external-routes":
            _print_json([route.to_dict() for route in service.external_routes()])
            return 0
        if args.command == "dry-quote":
            prepared = service.dry_quote(
                source_asset=args.source_asset,
                amount=args.amount,
                recipient=args.recipient,
                refund_to=args.refund_to,
                source_chain=args.source_chain,
                deposit_type=args.deposit_type,
                slippage_bps=args.slippage_bps,
                deadline_minutes=args.deadline_minutes,
            )
            _print_json(prepared.to_dict())
            return 0
        if args.command == "prepare-swap":
            prepared = service.prepare_swap(
                source_asset=args.source_asset,
                amount=args.amount,
                recipient=args.recipient,
                refund_to=args.refund_to,
                deposit_type=args.deposit_type,
                slippage_bps=args.slippage_bps,
                deadline_minutes=args.deadline_minutes,
            )
            _print_json(prepared.to_dict())
            return 0
        if args.command == "deposit-instructions":
            _print_json(service.deposit_instructions(args.quote_id).to_dict())
            return 0
        if args.command == "record-deposit":
            quote = service.record_deposit(args.quote_id, args.tx_hash, submit=args.submit)
            _print_json(service.quote_summary(quote))
            return 0
        if args.command == "status":
            quote = service.refresh_status(
                args.quote_id,
                max_attempts=args.max_attempts,
                interval_seconds=args.interval,
            )
            _print_json(service.quote_summary(quote))
            return 0
        if args.command == "capture-pre-transfer-balance":
            _print_json(service.capture_pre_transfer_balance(args.quote_id).to_dict())
            return 0
        if args.command == "verify-balance":
            quote = service.verify_balance(args.quote_id)
            _print_json(service.quote_summary(quote))
            return 0
        if args.command == "funding":
            _print_json(service.get_available_collateral(args.account))
            return 0
        if args.command == "show":
            _print_json(service.quote_summary(service.get_quote(args.quote_id)))
            return 0
        if args.command == "list":
            _print_json([service.quote_summary(item) for item in service.list_quotes(limit=args.limit)])
            return 0
        parser.error(f"unknown command: {args.command}")
        return 2
    except (ValidationError, TidepoolError, FundingStoreError, NearRpcError) as exc:
        payload = exc.as_dict() if hasattr(exc, "as_dict") else {"message": str(exc)}
        print(json.dumps({"error": payload}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
