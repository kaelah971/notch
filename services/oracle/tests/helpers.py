"""Shared helpers for S3B tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from services.trend_radar.http import FetchResult, FixtureFetcher
from services.trend_radar.models import jsonable

from services.oracle.rules import day_end, day_start, rule_digest, to_ns
from services.oracle.service import OracleConfig, OracleService
from services.oracle.fixture_fetcher import OracleFixtureFetcher
from services.oracle.store import OracleStore

FIXED_NOW = datetime(2026, 11, 12, 2, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 18, 0, 0, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]
S3A_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "s3a_live_scan_20261112.json"
CONTRACT_CONFIG = {
    "owner": "notch-dev.testnet",
    "operator": "notch-dev.testnet",
    "resolver": "notch-dev.testnet",
    "collateral_token": "usdc.tidepool-sandbox.testnet",
    "min_entry_amount": "1000000",
    "entries_paused": False,
    "market_count": 0,
    "fee_bps": 0,
}


def fixture_fetcher(now: datetime = FIXED_NOW) -> OracleFixtureFetcher:
    return OracleFixtureFetcher(FIXTURES, now_fn=lambda: now)


def temp_data_dir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory()


def make_service(
    data_dir: str | Path,
    *,
    now: datetime = FIXED_NOW,
    fetcher: Any | None = None,
    calibration_end: str = "2026-11-10",
) -> tuple[OracleService, OracleStore, Any]:
    fetcher = fetcher or fixture_fetcher(now)
    store = OracleStore(Path(data_dir) / "oracle.sqlite3")
    service = OracleService(
        fetcher=fetcher,
        store=store,
        config=OracleConfig(
            data_dir=str(data_dir),
            s3a_evidence_path=str(S3A_EVIDENCE),
            calibration_end=calibration_end,
        ),
        now_fn=lambda: now,
    )
    return service, store, fetcher


def build_demo(data_dir: str | Path, *, now: datetime = FIXED_NOW) -> dict[str, Any]:
    service, store, fetcher = make_service(data_dir, now=now)
    try:
        return service.demo(now=now)
    finally:
        store.close()


def fake_market(
    rule: dict[str, Any],
    *,
    totals: tuple[str, str] = ("1000000", "1000000"),
    status: str = "closed",
    **overrides: Any,
) -> dict[str, Any]:
    market = {
        "market_id": rule["market_id"],
        "mode": rule["mode"],
        "question": rule["question"],
        "choices": rule["choices"],
        "source_id": rule["source"]["id"],
        "rule_hash": rule_digest(rule),
        "open_at": rule["market_timing"]["open_at_ns"],
        "close_at": rule["market_timing"]["close_at_ns"],
        "resolve_after": rule["market_timing"]["resolve_after_ns"],
        "status": status,
        "totals": list(totals),
        "escrow_total": str(sum(int(value) for value in totals)),
        "battle": None,
    }
    if rule["mode"] == "trend_battle":
        topic_a, topic_b = rule["topics"]
        market["battle"] = {
            "topic_a": {
                "topic_id": topic_a["topic_id"],
                "source_id": rule["source"]["id"],
                "project": "en.wikipedia.org",
                "article_title": topic_a["article_title"],
                "metric": "daily_pageviews_growth_comparison",
            },
            "topic_b": {
                "topic_id": topic_b["topic_id"],
                "source_id": rule["source"]["id"],
                "project": "en.wikipedia.org",
                "article_title": topic_b["article_title"],
                "metric": "daily_pageviews_growth_comparison",
            },
            "observation_start": str(
                to_ns(day_start(date.fromisoformat(rule["observation"]["baseline_date"])))
            ),
            "observation_end": str(
                to_ns(day_end(date.fromisoformat(rule["observation"]["target_date"])))
            ),
            "formula": "growth_comparison_v1",
            "min_baseline_views": str(rule["minimum_baseline_views"]),
            "tie_tolerance_bps": rule["formula"]["tie_tolerance_bps"],
            "tie_policy": "void",
        }
    market.update(overrides)
    return market


class StaticJsonFetcher:
    """Returns a fixed payload for any URL and records calls."""

    def __init__(self, payload: Any, *, fetched_at: datetime = FIXED_NOW):
        self.payload = payload
        self.fetched_at = fetched_at
        self.calls: list[str] = []

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        self.calls.append(url)
        text = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return FetchResult(
            data=self.payload,
            url=url,
            source=source,
            fetched_at=self.fetched_at,
            raw_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


class RaisingFetcher:
    def __init__(self, error: Exception):
        self.error = error

    def get_json(self, url: str, *, source: str, **kwargs: Any) -> FetchResult:
        raise self.error


def copy_rule(rule: dict[str, Any], **changes: Any) -> dict[str, Any]:
    copied = json.loads(json.dumps(rule))
    for path, value in changes.items():
        cursor = copied
        parts = path.split(".")
        for part in parts[:-1]:
            cursor = cursor[part]
        cursor[parts[-1]] = value
    return copied


def rule_from_demo(demo: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in demo["rules"] if item["name"] == name)
