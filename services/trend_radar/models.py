"""Versioned data models for the Trend Radar."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


CANDIDATE_SCHEMA = "notch.trend-radar.candidate/1"
PROPOSAL_SCHEMA = "notch.trend-radar.proposal/1"
SCAN_SCHEMA = "notch.trend-radar.scan/1"
SOURCE_SNAPSHOT_SCHEMA = "notch.trend-radar.source-snapshot/1"


class Category(str, Enum):
    CRYPTO = "Crypto & Web3"
    AI = "AI & Technology"
    GAMING = "Gaming & Entertainment"
    POP = "Pop Culture & People"
    NEWS = "News & Current Events"
    OTHER = "Other"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_MEASURABLE = "NOT_MEASURABLE"
    STALE = "STALE"
    REJECTED = "REJECTED"


class SourceName(str, Enum):
    WIKIMEDIA = "wikimedia"
    COINGECKO = "coingecko"
    HACKER_NEWS = "hackernews"


class SourceStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    CACHED = "cached"
    FAILED = "failed"
    SKIPPED = "skipped"


class MarketMode(str, Enum):
    TREND_TRADING = "trend_trading"
    TREND_BATTLE = "trend_battle"


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def jsonable(value: Any) -> Any:
    """Recursively convert dataclasses/enums/dates into JSON-safe values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


@dataclass
class RawObservation:
    source: str
    source_id: str
    title: str
    url: str
    observed_at: datetime
    metrics: dict[str, Any] = field(default_factory=dict)
    source_identity: dict[str, Any] = field(default_factory=dict)
    reporting_date: date | None = None
    raw_hash: str | None = None
    raw_ref: str | None = None


@dataclass
class SourceHealth:
    source: str
    status: SourceStatus
    attempted_at: datetime | None = None
    last_success_at: datetime | None = None
    error: str | None = None
    stale: bool = False
    cache_used: bool = False
    item_count: int = 0
    latency_ms: int | None = None
    rate_limited: bool = False
    detail: str | None = None


@dataclass
class SourceResult:
    source: str
    observations: list[RawObservation]
    context: dict[str, Any] = field(default_factory=dict)
    health: SourceHealth | None = None
    identity_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    snapshot: Any = None
    snapshot_fetched_at: datetime | None = None
    snapshot_hash: str | None = None
    use_cached_snapshot: bool = False


@dataclass
class SettlementCoverage:
    source: str = "wikimedia-pageviews-v1"
    project: str = "en.wikipedia.org"
    article: str | None = None
    page_id: int | None = None
    status: str = "not_checked"
    daily_views: list[dict[str, Any]] = field(default_factory=list)
    window_start: str | None = None
    window_end: str | None = None
    min_views: int | None = None
    mean_views: int | None = None
    min_baseline_views: int = 1000
    raw_hashes: list[str] = field(default_factory=list)
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def measurable(self) -> bool:
        return (
            self.status == "ok"
            and self.min_views is not None
            and self.min_views >= self.min_baseline_views
            and len(self.daily_views) >= 5
        )


@dataclass
class Candidate:
    schema_version: str
    candidate_id: str
    canonical_topic_id: str
    title: str
    category: Category
    aliases: list[str]
    source_identities: list[dict[str, Any]]
    discovery_evidence: list[dict[str, Any]]
    source_urls: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    observed_at: datetime
    discovery_signals: dict[str, Any]
    eligibility_status: EligibilityStatus
    eligibility_reasons: list[str]
    confidence: int
    reliability: str
    proposed_market_modes: list[str]
    settlement_coverage: SettlementCoverage | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class MarketProposal:
    schema_version: str
    proposal_id: str
    candidate_ids: list[str]
    mode: MarketMode
    status: ProposalStatus
    topic: str
    question: str
    source: dict[str, Any]
    observation_window: dict[str, Any]
    threshold_bps: int | None
    tie_tolerance_bps: int | None
    tie_policy: str | None
    formula: str | None
    measurement_limitations: list[str]
    finalization_required: str
    rule_hash: str | None
    created_at: datetime
    topics: list[dict[str, Any]] = field(default_factory=list)
    threshold_status: str | None = "UNVALIDATED_PROPOSAL"
    decision_reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


@dataclass
class ScanResult:
    schema_version: str
    scan_id: str
    scan_kind: str
    started_at: datetime
    completed_at: datetime
    scan_date: str
    source_health: list[SourceHealth]
    candidates: list[Candidate]
    proposals: list[MarketProposal]
    source_context: dict[str, Any]
    last_successful_update: datetime | None
    deduplicated: bool = False
    errors: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(self)
