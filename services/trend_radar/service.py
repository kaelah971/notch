"""Trend Radar orchestration and typed service interface."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

from .canonical import canonical_json, sha256_text, stable_id
from .dedupe import build_candidates
from .eligibility import evaluate_candidates
from .http import FixtureFetcher, LiveFetcher
from .models import (
    SCAN_SCHEMA,
    Decision,
    SettlementCoverage,
    SourceHealth,
    SourceResult,
    SourceStatus,
    ScanResult,
    iso_utc,
    now_utc,
    parse_iso,
)
from .proposals import build_proposals
from .ranking import rank_candidates
from .sources.coingecko import CoinGeckoAdapter
from .sources.hackernews import HackerNewsAdapter
from .sources.wikimedia import WikimediaAdapter
from .store import RadarStore


class ScanInProgress(RuntimeError):
    def __init__(self, scan_id: str) -> None:
        super().__init__(f"a radar scan is already running: {scan_id}")
        self.scan_id = scan_id


@dataclass
class ScanConfig:
    enable_wikimedia: bool = True
    enable_coingecko: bool = True
    enable_hackernews: bool = True
    wiki_top_limit: int = 40
    wiki_min_views: int = 10_000
    probe_limit: int = 12
    coverage_days: int = 7
    min_baseline_views: int = 1_000
    proposal_limit: int = 10
    battle_limit: int = 5
    threshold_bps: int = 1500
    tie_tolerance_bps: int = 50
    scan_cooldown_seconds: int = 600
    running_timeout_seconds: int = 900
    stale_after_days: int = 7

    def enabled_sources(self) -> list[str]:
        sources = []
        if self.enable_wikimedia:
            sources.append("wikimedia")
        if self.enable_coingecko:
            sources.append("coingecko")
        if self.enable_hackernews:
            sources.append("hackernews")
        return sources


class TrendRadarService:
    """Backend interface for future web/API consumers.

    All methods return JSON-safe dictionaries. No method creates a market,
    signs a transaction or writes settlement evidence.
    """

    def __init__(
        self,
        *,
        fetcher: LiveFetcher | FixtureFetcher,
        store: RadarStore,
        config: ScanConfig | None = None,
        now_fn: Callable[[], datetime] = now_utc,
        operator: str | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.store = store
        self.config = config or ScanConfig()
        self.now_fn = now_fn
        self.operator = operator or "local-operator"
        self.scan_kind = "fixture" if isinstance(fetcher, FixtureFetcher) else "live"

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def _fingerprint(self, scan_date: date) -> str:
        config = asdict(self.config)
        return sha256_text(
            canonical_json(
                {
                    "schema": SCAN_SCHEMA,
                    "sources": self.config.enabled_sources(),
                    "scan_date": scan_date.isoformat(),
                    "config": config,
                }
            )
        )

    def scan(self, *, force: bool = False) -> dict[str, Any]:
        now = self.now_fn()
        scan_date = now.date()
        fingerprint = self._fingerprint(scan_date)

        running = self.store.running_scan(
            now, timeout_seconds=self.config.running_timeout_seconds
        )
        if running:
            raise ScanInProgress(running["scan_id"])

        if not force:
            recent = self.store.recent_completed_scan(
                fingerprint,
                since=now - timedelta(seconds=self.config.scan_cooldown_seconds),
            )
            if recent:
                result = json.loads(recent["result_json"])
                result["deduplicated"] = True
                return result

        scan_id = stable_id("scan", f"{fingerprint}:{iso_utc(now)}")
        self.store.start_scan(
            scan_id, fingerprint, self.config.enabled_sources(), now
        )

        try:
            result = self._run_scan(scan_id, now, scan_date)
            self.store.complete_scan(scan_id, result, result.completed_at)
            return result.to_dict()
        except Exception as exc:
            self.store.fail_scan(scan_id, str(exc), self.now_fn())
            raise

    def _run_scan(
        self, scan_id: str, now: datetime, scan_date: date
    ) -> ScanResult:
        started = now
        errors: list[str] = []
        source_results: list[SourceResult] = []
        health_items: list[SourceHealth] = []

        wikimedia = (
            WikimediaAdapter(
                self.fetcher,
                top_limit=self.config.wiki_top_limit,
                min_views=self.config.wiki_min_views,
                min_baseline_views=self.config.min_baseline_views,
            )
            if self.config.enable_wikimedia
            else None
        )
        coingecko = (
            CoinGeckoAdapter(self.fetcher)
            if self.config.enable_coingecko
            else None
        )
        hackernews = (
            HackerNewsAdapter(self.fetcher)
            if self.config.enable_hackernews
            else None
        )

        adapters = [
            ("wikimedia", wikimedia),
            ("coingecko", coingecko),
            ("hackernews", hackernews),
        ]
        for source, adapter in adapters:
            if adapter is None:
                health = SourceHealth(
                    source=source,
                    status=SourceStatus.SKIPPED,
                    attempted_at=now,
                    item_count=0,
                    detail="Source disabled for this scan.",
                )
                health_items.append(health)
                self.store.save_source_health(health)
                continue
            try:
                result = adapter.fetch(now, scan_date)
            except Exception as exc:  # isolation: one provider cannot stop the scan
                errors.append(f"{source}: {exc}")
                health = SourceHealth(
                    source=source,
                    status=SourceStatus.FAILED,
                    attempted_at=now,
                    error=str(exc),
                    item_count=0,
                    detail="Provider exception isolated; other sources continued.",
                )
                result = SourceResult(source=source, observations=[], health=health)
            source_results.append(result)
            health = result.health or SourceHealth(
                source=source,
                status=SourceStatus.FAILED,
                attempted_at=now,
                error="adapter returned no health",
            )
            health_items.append(health)
            if health.status == SourceStatus.FAILED and health.error:
                message = f"{source}: {health.error}"
                if message not in errors:
                    errors.append(message)
            if result.snapshot is not None and not result.use_cached_snapshot:
                self.store.save_source_snapshot(
                    source,
                    result.snapshot,
                    result.snapshot_fetched_at or now,
                    result.snapshot_hash or "",
                    result.context.get("reporting_date"),
                )

        health_by_source = {item.source: item for item in health_items}

        previous = self.store.previous_first_seen()
        candidates = build_candidates(
            source_results, now=now, previous_first_seen=previous
        )
        # Preliminary rank decides which candidates get the bounded coverage probe.
        candidates = rank_candidates(candidates, health_by_source, now)

        coverage_by_candidate: dict[str, SettlementCoverage] = {}
        probed_ids: set[str] = set()
        identity_error: str | None = None
        wiki_context = next(
            (r.context for r in source_results if r.source == "wikimedia"), {}
        )
        reporting_date_value = wiki_context.get("reporting_date")
        try:
            probe_end_date = (
                date.fromisoformat(reporting_date_value)
                if reporting_date_value
                else scan_date - timedelta(days=1)
            )
        except ValueError:
            probe_end_date = scan_date - timedelta(days=1)
        probe_articles = [
            candidate
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    -int(item.discovery_signals.get("score", 0)),
                    item.candidate_id,
                ),
            )
            if candidate.discovery_signals.get("settlement_article")
        ][: self.config.probe_limit]

        if wikimedia is not None and probe_articles:
            missing_articles = [
                str(candidate.discovery_signals["settlement_article"])
                for candidate in probe_articles
                if candidate.discovery_signals.get("settlement_page_id") is None
            ]
            resolved: dict[str, dict[str, Any]] = {}
            if missing_articles:
                resolved, identity_error = wikimedia.resolve_articles(
                    sorted(set(missing_articles))
                )
                if identity_error:
                    errors.append(f"wikimedia identity: {identity_error}")
            for candidate in probe_articles:
                article = str(candidate.discovery_signals["settlement_article"])
                page_id = candidate.discovery_signals.get("settlement_page_id")
                if page_id is None and article in resolved:
                    page_id = resolved[article].get("page_id")
                    candidate.discovery_signals["settlement_page_id"] = page_id
                coverage = wikimedia.probe_pageviews(
                    article=article,
                    page_id=page_id,
                    end_date=probe_end_date,
                    days=self.config.coverage_days,
                )
                coverage_by_candidate[candidate.candidate_id] = coverage
                probed_ids.add(candidate.candidate_id)
                if coverage.status not in {"ok", "insufficient_baseline"}:
                    errors.append(
                        f"coverage {candidate.title!r}: {coverage.status} "
                        f"{coverage.error or ''}".strip()
                    )

        evaluate_candidates(
            candidates,
            health_by_source=health_by_source,
            coverage_by_candidate=coverage_by_candidate,
            probed_ids=probed_ids,
            now=now,
            stale_after_days=self.config.stale_after_days,
        )
        # Final ranks include settlement coverage and eligibility confidence.
        candidates = rank_candidates(candidates, health_by_source, now)

        proposals = build_proposals(
            candidates,
            scan_date=scan_date,
            now=now,
            threshold_bps=self.config.threshold_bps,
            tie_tolerance_bps=self.config.tie_tolerance_bps,
            proposal_limit=self.config.proposal_limit,
            battle_limit=self.config.battle_limit,
        )
        for proposal in proposals:
            self.store.apply_existing_decision(proposal)
            self.store.upsert_proposal(proposal, now)

        for candidate in candidates:
            self.store.upsert_candidate(candidate)
        for health in health_items:
            self.store.save_source_health(health)
        persisted_health = {row["source"]: row for row in self.store.source_health()}
        for health in health_items:
            if health.last_success_at is None:
                stored = persisted_health.get(health.source, {}).get("last_success_at")
                if stored:
                    health.last_success_at = parse_iso(stored)

        coverage_summary = [
            {
                "candidate_id": candidate.candidate_id,
                "title": candidate.title,
                "article": candidate.discovery_signals.get("settlement_article"),
                "page_id": candidate.discovery_signals.get("settlement_page_id"),
                "status": coverage.status,
                "window_start": coverage.window_start,
                "window_end": coverage.window_end,
                "min_views": coverage.min_views,
                "mean_views": coverage.mean_views,
                "min_baseline_views": coverage.min_baseline_views,
                "error": coverage.error,
            }
            for candidate in candidates
            if (coverage := coverage_by_candidate.get(candidate.candidate_id))
        ]

        source_context = {
            "wikimedia": next(
                (r.context for r in source_results if r.source == "wikimedia"), {}
            ),
            "coingecko": next(
                (r.context for r in source_results if r.source == "coingecko"), {}
            ),
            "hackernews": next(
                (r.context for r in source_results if r.source == "hackernews"), {}
            ),
            "coverage_probes": coverage_summary,
            "identity_error": identity_error,
            "probe_limit": self.config.probe_limit,
            "note": (
                "Discovery data is separate from financial settlement. CoinGecko and "
                "Hacker News never become settlement sources."
            ),
        }

        completed = self.now_fn()
        result = ScanResult(
            schema_version=SCAN_SCHEMA,
            scan_id=scan_id,
            scan_kind=self.scan_kind,
            started_at=started,
            completed_at=completed,
            scan_date=scan_date.isoformat(),
            source_health=health_items,
            candidates=candidates,
            proposals=proposals,
            source_context=source_context,
            last_successful_update=self.store.last_successful_update(),
            errors=errors,
            config=asdict(self.config),
        )
        return result

    # ------------------------------------------------------------------
    # Read and review interface
    # ------------------------------------------------------------------
    def list_candidates(
        self,
        *,
        category: str | None = None,
        eligibility: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.store.list_candidates(
            category=category, eligibility=eligibility, limit=limit
        )

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        return self.store.get_candidate(candidate_id)

    def list_proposals(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.store.list_proposals(status=status, limit=limit)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return self.store.get_proposal(proposal_id)

    def review_proposal(
        self,
        proposal_id: str,
        decision: Decision | str,
        reason: str,
        *,
        operator: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(decision, str):
            decision = Decision(decision)
        return self.store.review_proposal(
            proposal_id,
            decision,
            reason,
            operator or self.operator,
            self.now_fn(),
        )

    def source_health(self) -> list[dict[str, Any]]:
        return self.store.source_health()

    def last_successful_update(self) -> datetime | None:
        return self.store.last_successful_update()
