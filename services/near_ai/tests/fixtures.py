"""Deterministic fixtures for S5 NEAR AI brief tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CANDIDATE_ID = "cand_b279c92126deeecb4beb"
MARKET_ID = "s3b-replay-trend-nvidia-20261103-20261110"


def candidate() -> dict[str, Any]:
    return {
        "schema_version": "notch.trend-radar.candidate/1",
        "candidate_id": CANDIDATE_ID,
        "canonical_topic_id": "entity:nvidia",
        "title": "Nvidia",
        "category": "AI & Technology",
        "aliases": ["Nvidia"],
        "source_identities": [],
        "discovery_evidence": [
            {
                "source": "wikimedia",
                "source_id": "wikimedia:en.wikipedia.org:Nvidia",
                "title": "Nvidia",
                "url": "https://en.wikipedia.org/wiki/Nvidia",
                "observed_at": "2026-11-10T23:59:59Z",
                "metrics": {
                    "views": 123851,
                    "rank": 17,
                    "reporting_date": "2026-11-10",
                    "page_id": 39120,
                },
                "raw_hash": "6dd62760d823d9d70685773f4c164935b2683d3c4f47a0e02cfc0e0d8c9c9ae5",
            },
            {
                "source": "hackernews",
                "source_id": "hn:story:50459703",
                "title": "Nvidia is preparing to oust Jensen Huang",
                "url": "https://www.wsj.com/business/nvidia-is-preparing-to-oust-nvidia-ceo-jensen-huang-30f421ad",
                "observed_at": "2026-11-12T00:21:10.784731Z",
                "metrics": {"points": 338, "comments": 314},
                "raw_hash": "d3c9a5b1eea37e90748623a1a0104853cf4ec9bb25eb89c450d464f75926950a",
            },
        ],
        "source_urls": [
            "https://en.wikipedia.org/wiki/Nvidia",
            "https://www.wsj.com/business/nvidia-is-preparing-to-oust-nvidia-ceo-jensen-huang-30f421ad",
        ],
        "first_seen_at": "2026-11-12T00:21:06.649036Z",
        "last_seen_at": "2026-11-12T00:21:06.649036Z",
        "observed_at": "2026-11-12T00:21:10.784731Z",
        "discovery_signals": {
            "source_count": 2,
            "sources": ["wikimedia", "hackernews"],
            "score": 85,
            "score_components": {"prominence": 20, "settlement_coverage": 25},
        },
        "eligibility_status": "ELIGIBLE",
        "eligibility_reasons": ["eligible_settlement_coverage"],
        "confidence": 80,
        "reliability": "medium",
        "proposed_market_modes": ["trend_trading", "trend_battle"],
        "settlement_coverage": {
            "source": "wikimedia-pageviews-v1",
            "project": "en.wikipedia.org",
            "article": "Nvidia",
            "page_id": 39120,
            "status": "ok",
            "daily_views": [
                {"date": "2026-11-04", "views": 4112, "timestamp": "2026110400"},
                {"date": "2026-11-05", "views": 4743, "timestamp": "2026110500"},
                {"date": "2026-11-06", "views": 4626, "timestamp": "2026110600"},
                {"date": "2026-11-07", "views": 5535, "timestamp": "2026110700"},
                {"date": "2026-11-08", "views": 17886, "timestamp": "2026110800"},
                {"date": "2026-11-09", "views": 142333, "timestamp": "2026110900"},
                {"date": "2026-11-10", "views": 123851, "timestamp": "2026111000"},
            ],
            "window_start": "2026-11-04",
            "window_end": "2026-11-10",
            "min_views": 4112,
            "mean_views": 43298,
            "min_baseline_views": 1000,
            "raw_hashes": ["95e0e5f62b22c8c49acebb39c6a73cf637273f59948d96289eecbb3d79ccf16e"],
            "notes": [
                "Daily Wikimedia pageviews, all-access/user, UTC full days.",
                "This is an eligibility probe, not finalized settlement evidence.",
            ],
        },
        "notes": ["Eligible for PROPOSED market drafts only."],
    }


def candidate_without_coverage() -> dict[str, Any]:
    data = deepcopy(candidate())
    data.pop("settlement_coverage", None)
    data["discovery_evidence"] = data["discovery_evidence"][:1]
    data["discovery_signals"]["source_count"] = 1
    return data


def rule_trend() -> dict[str, Any]:
    return {
        "schema_version": "notch.market-rule/2",
        "rule_version": "s3b-oracle/1",
        "market_id": MARKET_ID,
        "mode": "trend_trading",
        "question": (
            "HISTORICAL REPLAY (not a forecast): Will daily en.wikipedia.org pageviews "
            "for Nvidia grow by at least 13.50% on the full UTC day 2026-11-10 versus "
            "the full UTC day 2026-11-03?"
        ),
        "choices": ["UP", "DOWN"],
        "source": {
            "id": "wikimedia-pageviews-v1",
            "provider": "Wikimedia Analytics API",
            "project": "en.wikipedia.org",
            "access": "all-access",
            "agent": "user",
            "metric": "daily_pageviews",
            "granularity": "daily",
            "timezone": "UTC",
            "article": "Nvidia",
        },
        "topics": [
            {
                "topic_id": "nvidia",
                "article_title": "Nvidia",
                "page_id": 39120,
                "source_url": "https://en.wikipedia.org/wiki/Nvidia",
            }
        ],
        "observation": {
            "baseline_date": "2026-11-03",
            "target_date": "2026-11-10",
            "baseline_window_utc": "2026-11-03T00:00:00Z/2026-11-03T23:59:59Z",
            "target_window_utc": "2026-11-10T00:00:00Z/2026-11-10T23:59:59Z",
            "replay": True,
            "replay_label": "HISTORICAL_REPLAY",
        },
        "formula": {
            "version": "growth-threshold-v1",
            "growth_bps": "floor((target_views - baseline_views) * 10000 / baseline_views)",
            "threshold_bps": 1350,
            "up_if": "growth_bps >= threshold_bps",
            "down_if": "growth_bps < threshold_bps",
        },
        "minimum_baseline_views": 1000,
        "invalidation_policy": "refund_on_void",
        "missing_data_policy": "void",
        "resolution_eligibility_utc": "2026-11-17T12:00:00Z",
        "market_timing": {
            "open_at_ns": "1794452400000000000",
            "close_at_ns": "1794787140000000000",
            "resolve_after_ns": "1794916800000000000",
        },
        "contract": {
            "network": "testnet",
            "account": "market.notch-dev.testnet",
            "collateral_token": "usdc.tidepool-sandbox.testnet",
        },
        "candidate": {"candidate_ids": [CANDIDATE_ID]},
    }


def evidence_trend() -> dict[str, Any]:
    return {
        "schema_version": "notch.oracle.evidence/1",
        "market_id": MARKET_ID,
        "rule_hash": "sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b",
        "mode": "trend_trading",
        "resolver_version": "notch-s3b/0.1.0",
        "source": {"id": "wikimedia-pageviews-v1"},
        "topics": [{"topic_id": "nvidia", "article_title": "Nvidia", "page_id": 39120}],
        "observation": {
            "baseline_date": "2026-11-03",
            "target_date": "2026-11-10",
            "baseline_window_utc": "2026-11-03T00:00:00Z/2026-11-03T23:59:59Z",
            "target_window_utc": "2026-11-10T00:00:00Z/2026-11-10T23:59:59Z",
            "replay": True,
            "replay_label": "HISTORICAL_REPLAY",
        },
        "observations": {
            "nvidia": {
                "article": "Nvidia",
                "page_id": 39120,
                "baseline": {
                    "date": "2026-11-03",
                    "views": 4743,
                    "source_url": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Nvidia/daily/20260901/20261110",
                    "retrieved_at": "2026-11-12T01:07:34.707435Z",
                    "raw_response_hash": "f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2",
                },
                "target": {
                    "date": "2026-11-10",
                    "views": 123851,
                    "source_url": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Nvidia/daily/20260901/20261110",
                    "retrieved_at": "2026-11-12T01:07:34.707435Z",
                    "raw_response_hash": "f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2",
                },
            }
        },
        "calculation": {
            "outcome": "UP",
            "baseline_views": 4743,
            "target_views": 123851,
            "growth_bps": 251123,
            "threshold_bps": 1350,
            "minimum_baseline_views": 1000,
        },
        "outcome": "UP",
        "invalidity_reason": None,
        "retrieved_at": "2026-11-12T01:07:34.707435Z",
        "raw_source_hashes": ["f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2"],
        "integrity_note": "The evidence digest proves recorded-payload integrity, not organic attention.",
        "evidence_digest": "sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2",
    }


def valid_ai_content(context) -> dict[str, Any]:
    refs = [ref.ref_id for ref in context.evidence_references]
    if context.brief_type == "market":
        return {
            "headline": "Historical replay: Nvidia outcome UP",
            "summary": (
                "The frozen rule records 4,743 baseline views and 123,851 target views; "
                "the outcome is UP."
            ),
            "observed_signals": [
                {
                    "text": "Nvidia recorded 4,743 views on 2026-11-03 and 123,851 views on 2026-11-10.",
                    "kind": "FACT",
                    "evidence_refs": [refs[2]] if len(refs) > 2 else [refs[0]],
                }
            ],
            "notable_changes": [],
            "uncertainty": [
                {
                    "text": "This is a historical replay, not a forecast.",
                    "kind": "UNKNOWN",
                    "evidence_refs": [],
                }
            ],
            "missing_evidence": ["No sentiment data is included."],
            "suggested_research_questions": ["What events coincided with the change?"],
        }
    return {
        "headline": "Nvidia drew 123,851 views on 2026-11-10",
        "summary": (
            "Nvidia is an ELIGIBLE candidate with 2 sources. "
            "This is attention, not sentiment."
        ),
        "observed_signals": [
            {
                "text": "Wikimedia recorded 123,851 daily pageviews for Nvidia on 2026-11-10 (rank 17).",
                "kind": "FACT",
                "evidence_refs": [refs[0]],
            },
            {
                "text": "Hacker News recorded 338 points and 314 comments.",
                "kind": "FACT",
                "evidence_refs": [refs[1]],
            },
        ],
        "notable_changes": [
            {
                "text": "Daily views moved from 4,112 to 123,851.",
                "kind": "FACT",
                "evidence_refs": [refs[3]] if len(refs) > 3 else [refs[0]],
            }
        ],
        "uncertainty": [
            {
                "text": "Pageviews measure attention, not sentiment.",
                "kind": "UNKNOWN",
                "evidence_refs": [],
            }
        ],
        "missing_evidence": ["No social-post content is included."],
        "suggested_research_questions": ["What events coincided with the change?"],
    }
