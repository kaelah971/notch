"""Versioned data models for the S3B oracle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

RULE_SCHEMA = "notch.market-rule/2"
CALIBRATION_SCHEMA = "notch.oracle.calibration/1"
EVIDENCE_SCHEMA = "notch.oracle.evidence/1"
PLAN_SCHEMA = "notch.oracle.resolution-plan/1"
REVIEW_SCHEMA = "notch.oracle.review/1"
RESOLVER_VERSION = "notch-s3b/0.1.0"


@dataclass
class DayObservation:
    date: str
    views: int
    timestamp: str
    observation_hash: str
    raw_response_hash: str
    retrieved_at: datetime
    source_url: str
    project: str = "en.wikipedia.org"
    article: str = ""
    access: str = "all-access"
    agent: str = "user"


@dataclass
class PageviewsRange:
    article: str
    project: str
    start_date: str
    end_date: str
    source_url: str
    observations: dict[str, DayObservation] = field(default_factory=dict)
    missing_dates: list[str] = field(default_factory=list)
    duplicate_dates: list[str] = field(default_factory=list)
    raw_response_hash: str = ""
    retrieved_at: datetime | None = None
    error: str | None = None
    item_errors: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return (
            self.error is None
            and not self.missing_dates
            and not self.duplicate_dates
            and bool(self.observations)
        )


@dataclass
class CalibrationReport:
    schema_version: str
    mode: str
    article: str | None
    project: str
    baseline_date: str | None
    target_date: str | None
    calibration_start: str
    calibration_end: str
    calibration_days: int
    min_baseline_views: int
    observation_status: str
    baseline_views: int | None
    target_views: int | None
    weekly_growth_bps: dict[str, int]
    weekly_growth_stats: dict[str, int | None]
    daily_growth_stats: dict[str, int | None]
    suggested_threshold_bps: int | None
    threshold_candidates: dict[str, int | None]
    threshold_policy: str
    up_frequency_at_threshold: int | None
    status: str
    reasons: list[str]
    missing_dates: list[str]
    source_queries: list[str]
    source_raw_hashes: list[str]
    retrieved_at: datetime | None
    report_digest: str | None = None
    topic_b_article: str | None = None
    growth_a_bps: int | None = None
    growth_b_bps: int | None = None
    difference_bps: int | None = None
    abs_difference_stats: dict[str, int | None] = field(default_factory=dict)
    suggested_tie_tolerance_bps: int | None = None
    tie_frequency_at_suggestion: int | None = None
    tie_policy: str | None = None


@dataclass
class FrozenRule:
    rule_hash: str
    rule: dict[str, Any]
    status: str
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_reason: str | None = None


@dataclass
class Evidence:
    schema_version: str
    market_id: str
    rule_hash: str
    mode: str
    resolver_version: str
    source: dict[str, Any]
    topics: list[dict[str, Any]]
    observation: dict[str, Any]
    observations: dict[str, dict[str, Any]]
    calculation: dict[str, Any]
    outcome: str
    invalidity_reason: str | None
    retrieved_at: str
    raw_source_hashes: list[str]
    integrity_note: str
    evidence_digest: str


@dataclass
class ResolutionPlan:
    schema_version: str
    job_id: str
    market_id: str
    rule_hash: str
    mode: str
    evidence_digest: str
    outcome: str
    action: str
    status: str
    contract_call: dict[str, Any] | None
    near_cli_command_template: str | None
    blockers: list[str]
    warnings: list[str]
    onchain_market: dict[str, Any] | None
    prepared_at: str
    idempotent: bool = False


@dataclass
class ValidationReport:
    schema_version: str
    candidate_ids: list[str]
    title: str
    canonical_topic_ids: list[str]
    category: str | None
    measurement_valid: bool
    measurement_status: str
    market_interest: str
    market_interest_reasons: list[str]
    recognizable_topic: bool
    recognizable_reasons: list[str]
    sensitivity_flags: list[dict[str, Any]]
    relationship_flags: list[dict[str, Any]]
    ambiguous_mapping: bool
    ambiguity_reasons: list[str]
    operator_approval_required: bool
    recommendation: str
    reasons: list[str]
    sources: list[dict[str, Any]]
