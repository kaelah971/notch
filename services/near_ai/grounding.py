"""Grounding S5 briefs in existing S3A candidates and S3B evidence.

The prompt context is assembled from stored Radar candidates and frozen oracle
rules/evidence.  No new discovery or oracle computation is performed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.oracle.store import OracleStore
from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.store import RadarStore

from .models import (
    BriefContext,
    BriefDraft,
    BriefType,
    ClaimKind,
    EvidenceClaim,
    EvidenceReference,
    PROMPT_VERSION,
    ResolutionExplanation,
)


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"(?<![\w])(-?\d[\d,]*(?:\.\d+)?)")


class GroundingError(ValueError):
    pass


def load_candidate(candidate_id: str, radar_db: str | Path) -> dict[str, Any]:
    path = Path(radar_db)
    if not path.exists():
        raise GroundingError(f"Radar database not found: {path}")
    store = RadarStore(path)
    try:
        candidate = store.get_candidate(candidate_id)
    finally:
        store.close()
    if not candidate:
        raise GroundingError(f"candidate not found: {candidate_id}")
    return candidate


def load_market(market_id: str, oracle_db: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(oracle_db)
    if not path.exists():
        raise GroundingError(f"oracle database not found: {path}")
    store = OracleStore(path)
    try:
        rule = store.get_rule_by_market(market_id)
        evidence = store.list_evidence(market_id=market_id)
    finally:
        store.close()
    if not rule:
        raise GroundingError(f"frozen rule not found: {market_id}")
    if not evidence:
        raise GroundingError(f"evidence not found: {market_id}")
    return rule, evidence[0]["evidence"]


def build_radar_context(candidate: dict[str, Any]) -> BriefContext:
    topic = str(candidate.get("title") or "Unknown topic")
    candidate_id = str(candidate.get("candidate_id"))
    refs: list[EvidenceReference] = []
    ref_by_key: dict[str, str] = {}

    def add_ref(source: str, title: str, url: str | None, observed_at: str | None, raw_hash: str | None, key: str) -> str:
        if key in ref_by_key:
            return ref_by_key[key]
        ref_id = f"radar:{candidate_id}:{len(refs) + 1}"
        refs.append(
            EvidenceReference(
                ref_id=ref_id,
                source=source,
                title=title,
                url=url,
                observed_at=observed_at,
                raw_hash=raw_hash,
            )
        )
        ref_by_key[key] = ref_id
        return ref_id

    signals: list[dict[str, Any]] = []
    observed: list[tuple[str, str]] = []
    for item in candidate.get("discovery_evidence", []):
        source = str(item.get("source") or "unknown")
        title = str(item.get("title") or topic)
        metrics = item.get("metrics") or {}
        ref_id = add_ref(
            source,
            title,
            item.get("url"),
            item.get("observed_at"),
            item.get("raw_hash"),
            f"{source}:{item.get('source_id') or title}:{item.get('observed_at')}",
        )
        signal = {
            "source": source,
            "title": title,
            "url": item.get("url"),
            "observed_at": item.get("observed_at"),
            "metrics": metrics,
            "evidence_ref": ref_id,
        }
        signals.append(signal)
        if source == "wikimedia" and "views" in metrics:
            observed.append((
                f"Wikimedia recorded {_fmt(metrics['views'])} daily pageviews for {title} "
                f"on {metrics.get('reporting_date') or item.get('observed_at')} "
                f"(rank {_fmt(metrics.get('rank'))}).",
                ref_id,
            ))
        elif source == "hackernews":
            observed.append((
                f"Hacker News story \"{title}\" recorded {_fmt(metrics.get('points'))} points "
                f"and {_fmt(metrics.get('comments'))} comments.",
                ref_id,
            ))
        elif source == "coingecko":
            observed.append((
                f"CoinGecko listed {title} at trending rank {_fmt(metrics.get('trending_rank'))}.",
                ref_id,
            ))
    coverage = candidate.get("settlement_coverage") or {}
    daily = coverage.get("daily_views") or []
    coverage_ref = None
    if coverage:
        coverage_ref = add_ref(
            "wikimedia-pageviews",
            f"{coverage.get('article') or topic} daily pageviews",
            None,
            coverage.get("window_end"),
            (coverage.get("raw_hashes") or [None])[0],
            f"coverage:{coverage.get('article')}:{coverage.get('window_start')}:{coverage.get('window_end')}",
        )
        if coverage.get("min_views") is not None:
            observed.append((
                f"The coverage window {coverage.get('window_start')} to {coverage.get('window_end')} "
                f"had a minimum of {_fmt(coverage.get('min_views'))} daily views and a mean of "
                f"{_fmt(coverage.get('mean_views'))} daily views.",
                coverage_ref,
            ))
    notable: list[tuple[str, str]] = []
    if daily:
        first, last = daily[0], daily[-1]
        notable.append((
            f"Daily views moved from {_fmt(first.get('views'))} on {first.get('date')} "
            f"to {_fmt(last.get('views'))} on {last.get('date')}.",
            coverage_ref or refs[0].ref_id,
        ))
    latest = daily[-1] if daily else None
    if latest:
        headline = f"{topic}: {_fmt(latest.get('views'))} Wikimedia views on {latest.get('date')}"
    else:
        headline = f"{topic}: S3A Radar candidate with {_fmt(candidate.get('discovery_signals', {}).get('source_count'))} source(s)"
    source_count = candidate.get("discovery_signals", {}).get("source_count")
    eligibility = candidate.get("eligibility_status", "UNKNOWN")
    summary = (
        f"{topic} is an {eligibility} S3A candidate with {_fmt(source_count)} source(s). "
        "The measurements describe attention, not sentiment or price direction."
    )
    measurement_window = {
        "start": coverage.get("window_start") or candidate.get("observed_at"),
        "end": coverage.get("window_end") or candidate.get("observed_at"),
        "timezone": "UTC",
        "metric": "Wikimedia daily pageviews and Radar discovery signals",
    }
    data_as_of = str(candidate.get("observed_at") or "")
    uncertainty = [
        EvidenceClaim(
            "Pageviews measure attention, not sentiment or market direction.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
        EvidenceClaim(
            "S3A coverage is an eligibility probe, not finalized settlement evidence.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
        EvidenceClaim(
            "The brief does not establish a causal explanation for the observed change.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
    ]
    missing = [
        "No social-post content, search-intent data, or sentiment labels are included.",
        "No full source snapshot is embedded in the brief.",
        "No frozen market rule is attached to this Radar brief.",
    ]
    questions = [
        "What events coincided with the view changes?",
        "Are the same signals visible outside Wikimedia?",
        "Which frozen rule would make this topic measurable?",
    ]
    fallback = BriefDraft(
        headline=headline,
        summary=summary,
        observed_signals=[_claim(text, [ref_id]) for text, ref_id in observed],
        notable_changes=[_claim(text, [ref_id]) for text, ref_id in notable],
        uncertainty=uncertainty,
        missing_evidence=missing,
        suggested_research_questions=questions,
    )
    payload = {
        "brief_type": BriefType.RADAR.value,
        "topic": topic,
        "candidate_id": candidate_id,
        "category": candidate.get("category"),
        "eligibility_status": eligibility,
        "observed_at": candidate.get("observed_at"),
        "discovery_signals": candidate.get("discovery_signals") or {},
        "signals": signals,
        "coverage": coverage,
        "coverage_evidence_ref": coverage_ref,
        "source_urls": candidate.get("source_urls") or [],
        "notes": candidate.get("notes") or [],
        "measurement_window": measurement_window,
        "data_as_of": data_as_of,
        "evidence_references": [ref.to_dict() for ref in refs],
    }
    allowed_numbers, allowed_dates = _allowed_numbers(payload)
    return BriefContext(
        brief_type=BriefType.RADAR.value,
        topic=topic,
        candidate_id=candidate_id,
        market_id=None,
        measurement_window=measurement_window,
        data_as_of=data_as_of,
        evidence_references=refs,
        allowed_numbers=allowed_numbers,
        allowed_dates=allowed_dates,
        prompt_payload=payload,
        fallback=fallback,
        resolution=None,
        input_digest=_input_digest(payload, BriefType.RADAR.value),
    )


def build_market_context(rule_record: dict[str, Any], evidence: dict[str, Any]) -> BriefContext:
    rule = rule_record.get("rule", rule_record)
    market_id = str(rule["market_id"])
    topics = rule.get("topics") or []
    if topics:
        topic = " vs ".join(str(item.get("article_title") or item.get("topic_id")) for item in topics)
    else:
        topic = str(rule.get("source", {}).get("article") or market_id)
    refs: list[EvidenceReference] = []
    ref_by_key: dict[str, str] = {}

    def add_ref(source: str, title: str, url: str | None, observed_at: str | None, raw_hash: str | None, key: str) -> str:
        if key in ref_by_key:
            return ref_by_key[key]
        ref_id = f"market:{market_id}:{len(refs) + 1}"
        refs.append(
            EvidenceReference(
                ref_id=ref_id,
                source=source,
                title=title,
                url=url,
                observed_at=observed_at,
                raw_hash=raw_hash,
                kind="oracle",
            )
        )
        ref_by_key[key] = ref_id
        return ref_id

    rule_ref = add_ref(
        "s3b-rule",
        "Frozen S3B market rule",
        None,
        rule.get("created_at"),
        None,
        "rule",
    )
    evidence_ref = add_ref(
        "s3b-evidence",
        "Frozen S3B evidence receipt",
        None,
        evidence.get("retrieved_at"),
        None,
        "evidence",
    )
    observations = evidence.get("observations") or {}
    observed: list[tuple[str, str]] = []
    for topic_id, item in observations.items():
        article = item.get("article") or topic_id
        baseline = item.get("baseline") or {}
        target = item.get("target") or {}
        ref_id = add_ref(
            "wikimedia-pageviews-v1",
            f"{article} baseline and target",
            target.get("source_url"),
            target.get("retrieved_at"),
            target.get("raw_response_hash"),
            f"obs:{article}",
        )
        observed.append((
            f"{article} recorded {_fmt(baseline.get('views'))} views on {baseline.get('date')} "
            f"and {_fmt(target.get('views'))} views on {target.get('date')}.",
            ref_id,
        ))
    calculation = evidence.get("calculation") or {}
    mode = rule.get("mode")
    if mode == "trend_trading":
        calculation_text = (
            f"The calculation records growth of {_fmt(calculation.get('growth_bps'))} bps "
            f"against a {_fmt(calculation.get('threshold_bps'))} bps threshold; the outcome is "
            f"{evidence.get('outcome')}."
        )
    else:
        calculation_text = (
            f"The calculation records growth of {_fmt(calculation.get('growth_a_bps'))} bps for "
            f"{topics[0].get('article_title') if topics else 'topic A'} and "
            f"{_fmt(calculation.get('growth_b_bps'))} bps for "
            f"{topics[1].get('article_title') if len(topics) > 1 else 'topic B'}, a difference of "
            f"{_fmt(calculation.get('difference_bps'))} bps against a "
            f"{_fmt(calculation.get('tie_tolerance_bps'))} bps tie tolerance; the outcome is "
            f"{evidence.get('outcome')}."
        )
    observed.append((calculation_text, evidence_ref))
    resolution = _resolution_explanation(rule, evidence)
    measurement_window = {
        "baseline_date": evidence.get("observation", {}).get("baseline_date"),
        "target_date": evidence.get("observation", {}).get("target_date"),
        "baseline_window_utc": evidence.get("observation", {}).get("baseline_window_utc"),
        "target_window_utc": evidence.get("observation", {}).get("target_window_utc"),
        "replay": evidence.get("observation", {}).get("replay"),
    }
    headline = f"Historical replay: {topic} outcome {evidence.get('outcome')}"
    summary = (
        f"This is a historical replay, not a forecast. The frozen rule compares "
        f"{evidence.get('observation', {}).get('baseline_date')} with "
        f"{evidence.get('observation', {}).get('target_date')}; the recorded outcome is "
        f"{evidence.get('outcome')}."
    )
    uncertainty = [
        EvidenceClaim(
            "This is a historical replay, not a forecast.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
        EvidenceClaim(
            "Pageviews measure attention, not sentiment or market direction.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
        EvidenceClaim(
            "The evidence digest proves recorded-payload integrity, not organic attention.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
    ]
    missing = [
        "No social-post content, sentiment labels, or causal attribution is included.",
        "The brief does not alter the frozen rule, evidence digest, or outcome.",
    ]
    questions = [
        "What events coincided with the recorded change?",
        "How sensitive is the outcome to the frozen threshold or tie tolerance?",
        "What independent source would confirm the pattern?",
    ]
    fallback = BriefDraft(
        headline=headline,
        summary=summary,
        observed_signals=[_claim(text, [ref_id]) for text, ref_id in observed],
        notable_changes=[],
        uncertainty=uncertainty,
        missing_evidence=missing,
        suggested_research_questions=questions,
    )
    payload = {
        "brief_type": BriefType.MARKET.value,
        "topic": topic,
        "market_id": market_id,
        "rule": {
            "mode": rule.get("mode"),
            "question": rule.get("question"),
            "choices": rule.get("choices"),
            "source": rule.get("source"),
            "observation": rule.get("observation"),
            "formula": rule.get("formula"),
            "minimum_baseline_views": rule.get("minimum_baseline_views"),
            "invalidation_policy": rule.get("invalidation_policy"),
            "resolution_eligibility_utc": rule.get("resolution_eligibility_utc"),
        },
        "evidence": {
            "outcome": evidence.get("outcome"),
            "evidence_digest": evidence.get("evidence_digest"),
            "calculation": calculation,
            "observations": observations,
            "integrity_note": evidence.get("integrity_note"),
            "retrieved_at": evidence.get("retrieved_at"),
        },
        "resolution": resolution.to_dict(),
        "measurement_window": measurement_window,
        "data_as_of": evidence.get("retrieved_at"),
        "evidence_references": [ref.to_dict() for ref in refs],
    }
    allowed_numbers, allowed_dates = _allowed_numbers(payload)
    return BriefContext(
        brief_type=BriefType.MARKET.value,
        topic=topic,
        candidate_id=_first_candidate_id(rule),
        market_id=market_id,
        measurement_window=measurement_window,
        data_as_of=str(evidence.get("retrieved_at") or ""),
        evidence_references=refs,
        allowed_numbers=allowed_numbers,
        allowed_dates=allowed_dates,
        prompt_payload=payload,
        fallback=fallback,
        resolution=resolution,
        input_digest=_input_digest(payload, BriefType.MARKET.value),
    )


def _research_rule_payload(rule: dict[str, Any]) -> dict[str, Any]:
    source = rule.get("source") or {}
    return {
        "market_id": rule.get("market_id"),
        "mode": rule.get("mode"),
        "question": rule.get("question"),
        "choices": rule.get("choices"),
        "source": {
            key: source.get(key)
            for key in ("id", "provider", "project", "access", "agent", "metric", "granularity", "timezone", "article")
            if source.get(key) is not None
        },
        "topics": [
            {
                key: item.get(key)
                for key in ("topic_id", "article_title", "page_id", "source_url")
                if item.get(key) is not None
            }
            for item in (rule.get("topics") or [])
        ],
        "observation": rule.get("observation") or {},
        "formula": rule.get("formula") or {},
        "minimum_baseline_views": rule.get("minimum_baseline_views"),
        "invalidation_policy": rule.get("invalidation_policy"),
        "missing_data_policy": rule.get("missing_data_policy"),
    }


def _research_evidence_payload(evidence: dict[str, Any] | None, market_id: str) -> dict[str, Any] | None:
    if not evidence:
        return None
    observations: dict[str, Any] = {}
    for topic_id, item in (evidence.get("observations") or {}).items():
        compact_item: dict[str, Any] = {"article": item.get("article"), "page_id": item.get("page_id")}
        for key in ("baseline", "target"):
            observation = item.get(key) or {}
            if observation:
                compact_item[key] = {
                    "date": observation.get("date"),
                    "views": observation.get("views"),
                }
        observations[str(topic_id)] = compact_item
    return {
        "market_id": evidence.get("market_id"),
        "rule_hash": evidence.get("rule_hash"),
        "evidence_digest": evidence.get("evidence_digest"),
        "mode": evidence.get("mode"),
        "source": evidence.get("source"),
        "observation": evidence.get("observation"),
        "calculation": evidence.get("calculation"),
        "outcome": evidence.get("outcome"),
        "invalidity_reason": evidence.get("invalidity_reason"),
        "retrieved_at": evidence.get("retrieved_at"),
        "raw_source_hashes": evidence.get("raw_source_hashes"),
        "observations": observations,
    }


def _research_calibration_payload(item: dict[str, Any], source_id: str) -> dict[str, Any]:
    calibration = item.get("calibration") or {}
    return {
        "source_id": source_id,
        "kind": "calibration",
        "article": item.get("article"),
        "mode": item.get("mode"),
        "calibration": {
            key: calibration.get(key)
            for key in (
                "schema_version", "mode", "article", "project", "calibration_start", "calibration_end",
                "calibration_days", "min_baseline_views", "observation_status", "weekly_growth_stats",
                "daily_growth_stats", "suggested_threshold_bps", "threshold_policy", "status", "report_digest",
            )
            if calibration.get(key) is not None
        },
    }


def _research_replay_payload(item: dict[str, Any], source_id: str) -> dict[str, Any]:
    replay_rule = item.get("rule") or {}
    replay_evidence = item.get("evidence") or {}
    return {
        "source_id": source_id,
        "kind": "historical_replay",
        "market_id": item.get("market_id"),
        "rule": _research_rule_payload(replay_rule),
        "evidence": _research_evidence_payload(replay_evidence, str(item.get("market_id") or "")),
    }


def build_market_research_context(
    rule_record: dict[str, Any],
    evidence: dict[str, Any] | None,
    attention_snapshots: list[dict[str, Any]],
    historical_context: list[dict[str, Any]],
) -> BriefContext:
    """Build the explicit, two-sided market research packet."""
    rule = rule_record.get("rule", rule_record)
    market_id = str(rule.get("market_id") or rule_record.get("market_id"))
    topics = rule.get("topics") or []
    topic = " vs ".join(str(item.get("article_title") or item.get("topic_id")) for item in topics)
    if not topic:
        topic = str((rule.get("source") or {}).get("article") or market_id)
    refs: list[EvidenceReference] = []
    payload_observations: list[dict[str, Any]] = []
    observed_claims: list[EvidenceClaim] = []
    supporting_up: list[EvidenceClaim] = []
    supporting_down: list[EvidenceClaim] = []
    missing: list[str] = []

    def add_ref(
        ref_id: str,
        source: str,
        title: str,
        url: str | None,
        observed_at: str | None,
        raw_hash: str | None,
        kind: str,
    ) -> str:
        refs.append(
            EvidenceReference(
                ref_id=ref_id,
                source=source,
                title=title,
                url=url,
                observed_at=observed_at,
                raw_hash=raw_hash,
                kind=kind,
            )
        )
        return ref_id

    rule_ref = add_ref(
        f"market:{market_id}:rule",
        "notch-market-rule",
        "Published market rule",
        None,
        rule_record.get("created_at"),
        str(rule_record.get("rule_hash") or "") or None,
        "rule",
    )
    evidence_ref = None
    if evidence is not None:
        evidence_ref = add_ref(
            f"market:{market_id}:evidence",
            "notch-oracle-evidence",
            "Verified oracle evidence receipt",
            None,
            evidence.get("retrieved_at"),
            str(evidence.get("evidence_digest") or "") or None,
            "oracle",
        )

    for snapshot in sorted(attention_snapshots, key=lambda item: str(item.get("article") or "")):
        article = str(snapshot.get("article") or "topic")
        safe_article = re.sub(r"[^a-z0-9]+", "-", article.lower()).strip("-") or "topic"
        rows: list[dict[str, Any]] = []
        for item in sorted(snapshot.get("observations") or [], key=lambda value: str(value.get("date") or "")):
            date = str(item.get("date") or "")
            if not date or item.get("views") is None:
                continue
            ref_id = f"market:{market_id}:attention:{safe_article}:{date}"
            add_ref(
                ref_id,
                "wikimedia-pageviews-v1",
                f"{article} pageviews on {date}",
                item.get("source_url") or snapshot.get("source_url"),
                item.get("retrieved_at") or snapshot.get("retrieved_at"),
                item.get("raw_response_hash") or snapshot.get("raw_response_hash"),
                "measurement",
            )
            row = {
                "source_id": ref_id,
                "date": date,
                "views": item.get("views"),
            }
            rows.append(row)
        payload_observations.append({
            "article": article,
            "project": snapshot.get("project"),
            "access": snapshot.get("access"),
            "agent": snapshot.get("agent"),
            "window_start": snapshot.get("window_start"),
            "window_end": snapshot.get("window_end"),
            "source_status": snapshot.get("source_status"),
            "retrieved_at": snapshot.get("retrieved_at"),
            "missing_dates": snapshot.get("missing_dates") or [],
            "error": snapshot.get("error"),
            "observations": [{"date": row["date"], "views": row["views"]} for row in rows],
        })
        if snapshot.get("error"):
            missing.append(f"{article} attention observations were unavailable: {snapshot['error']}.")
        if snapshot.get("missing_dates"):
            missing.append(f"{article} has no supplied observation for {', '.join(snapshot['missing_dates'][:4])}.")
        if not rows:
            missing.append(f"No verified {article} pageview observations were supplied for the research window.")
            continue
        if len(rows) >= 2:
            observed_claims.append(EvidenceClaim(
                f"{article} pageviews moved from {_fmt(rows[0]['views'])} on {rows[0]['date']} to {_fmt(rows[-1]['views'])} on {rows[-1]['date']}.",
                ClaimKind.FACT.value,
                [rows[0]["source_id"], rows[-1]["source_id"]],
            ))
            if int(rows[-1]["views"]) >= int(rows[0]["views"]):
                supporting_up.append(EvidenceClaim(
                    f"The supplied {article} observations increased from {_fmt(rows[0]['views'])} to {_fmt(rows[-1]['views'])} across the available window; this is attention evidence, not a forecast of the target day.",
                    ClaimKind.INTERPRETATION.value,
                    [rows[0]["source_id"], rows[-1]["source_id"]],
                ))
            else:
                supporting_down.append(EvidenceClaim(
                    f"The supplied {article} observations decreased from {_fmt(rows[0]['views'])} to {_fmt(rows[-1]['views'])} across the available window; this is attention evidence, not a forecast of the target day.",
                    ClaimKind.INTERPRETATION.value,
                    [rows[0]["source_id"], rows[-1]["source_id"]],
                ))

    historical_payload: list[dict[str, Any]] = []
    historical_claims: list[EvidenceClaim] = []
    for index, item in enumerate(historical_context):
        source_id = str(item.get("source_id") or f"market:{market_id}:historical:{index + 1}")
        if item.get("kind") == "calibration":
            calibration = item.get("calibration") or {}
            add_ref(
                source_id,
                "notch-oracle-calibration",
                f"{item.get('article')} deterministic calibration ({item.get('mode')})",
                None,
                calibration.get("calibration_end"),
                (calibration.get("source_raw_hashes") or [None])[0],
                "historical_simulation",
            )
            historical_payload.append(_research_calibration_payload(item, source_id))
            stats = calibration.get("weekly_growth_stats") or {}
            if stats:
                historical_claims.append(EvidenceClaim(
                    f"Matching {item.get('article')} {item.get('mode')} calibration covered {_fmt(calibration.get('calibration_days'))} days from {calibration.get('calibration_start')} to {calibration.get('calibration_end')}; its p75 weekly growth was {_fmt(stats.get('p75'))} bps.",
                    ClaimKind.FACT.value,
                    [source_id],
                ))
        elif item.get("kind") == "historical_replay":
            replay_rule = item.get("rule") or {}
            replay_evidence = item.get("evidence") or {}
            add_ref(
                source_id,
                "notch-historical-replay",
                f"Matching historical replay {item.get('market_id')}",
                None,
                replay_evidence.get("retrieved_at"),
                replay_evidence.get("evidence_digest"),
                "historical_simulation",
            )
            historical_payload.append(_research_replay_payload(item, source_id))
            historical_claims.append(EvidenceClaim(
                f"Matching historical replay {item.get('market_id')} recorded outcome {replay_evidence.get('outcome')} under the same {replay_rule.get('mode')} methodology; it is historical context, not a forecast.",
                ClaimKind.FACT.value,
                [source_id],
            ))
    if not historical_claims:
        missing.append("No same-topic, same-methodology historical replay or calibration was supplied.")

    evidence_observations = evidence.get("observations") if evidence else {}
    if isinstance(evidence_observations, dict):
        for topic_id, item in evidence_observations.items():
            for key in ("baseline", "target"):
                observation = item.get(key) or {}
                if not observation:
                    continue
                ref_id = f"market:{market_id}:oracle:{topic_id}:{key}"
                add_ref(
                    ref_id,
                    "notch-oracle-evidence",
                    f"{item.get('article') or topic_id} {key} observation",
                    observation.get("source_url"),
                    observation.get("retrieved_at"),
                    observation.get("raw_response_hash"),
                    "oracle",
                )
                observed_claims.append(EvidenceClaim(
                    f"The verified receipt records {item.get('article') or topic_id} at {_fmt(observation.get('views'))} views on {observation.get('date')} ({key}).",
                    ClaimKind.FACT.value,
                    [ref_id, evidence_ref] if evidence_ref else [ref_id],
                ))

    observation = rule.get("observation") or {}
    formula = rule.get("formula") or {}
    baseline_date = observation.get("baseline_date")
    target_date = observation.get("target_date")
    supplied_dates = {row.get("date") for snapshot in payload_observations for row in snapshot.get("observations", [])}
    if baseline_date not in supplied_dates:
        missing.append(f"The rule baseline date {baseline_date} is not in the supplied current observation window.")
    if target_date not in supplied_dates:
        missing.append(f"The rule target date {target_date} is not in the supplied current observation window; no outcome is asserted.")

    if evidence:
        resolution = _resolution_explanation(rule, evidence)
    else:
        resolution = ResolutionExplanation(
            rule_hash=str(rule_record.get("rule_hash") or ""),
            evidence_digest="",
            mode=str(rule.get("mode") or ""),
            outcome="PENDING",
            text=(
                f"The published rule resolves {formula.get('up_if') or 'UP/DOWN according to the formula'} "
                f"using the full UTC-day baseline {baseline_date} and target {target_date}. "
                "The supplied observations do not include a finalized oracle receipt, so no market outcome is asserted."
            ),
            formula=str(formula.get("growth_bps") or formula),
            observation_window={
                "baseline_date": baseline_date,
                "target_date": target_date,
                "baseline_window_utc": observation.get("baseline_window_utc"),
                "target_window_utc": observation.get("target_window_utc"),
            },
        )

    if not supporting_up:
        supporting_up.append(EvidenceClaim(
            "The supplied evidence does not establish an UP case for the target rule.",
            ClaimKind.UNKNOWN.value,
            [],
        ))
    if not supporting_down:
        supporting_down.append(EvidenceClaim(
            "The supplied evidence does not establish a DOWN case for the target rule.",
            ClaimKind.UNKNOWN.value,
            [],
        ))
    assumptions = [
        EvidenceClaim(
            "The locked market rule, full UTC-day windows, and published threshold are used exactly as supplied.",
            ClaimKind.FACT.value,
            [rule_ref],
        ),
        EvidenceClaim(
            "Pageviews measure attention and do not establish sentiment, causality, price direction, or a calibrated probability.",
            ClaimKind.UNKNOWN.value,
            [],
        ),
    ]
    latest_observation_date = max(
        (str(row.get("date")) for snapshot in payload_observations for row in snapshot.get("observations", [])),
        default=None,
    )
    retrieved_values = [
        str(snapshot.get("retrieved_at"))
        for snapshot in payload_observations
        if snapshot.get("retrieved_at")
    ]
    data_as_of = max(retrieved_values, default=str(evidence.get("retrieved_at") if evidence else ""))
    measurement_window = {
        "baseline_date": baseline_date,
        "target_date": target_date,
        "baseline_window_utc": observation.get("baseline_window_utc"),
        "target_window_utc": observation.get("target_window_utc"),
        "observation_cutoff": latest_observation_date,
        "attention_window_start": min((str(item.get("window_start")) for item in attention_snapshots if item.get("window_start")), default=None),
        "attention_window_end": max((str(item.get("window_end")) for item in attention_snapshots if item.get("window_end")), default=None),
        "source": (rule.get("source") or {}).get("provider"),
    }
    fallback = BriefDraft(
        headline=f"{topic} research: source observations through {latest_observation_date or 'unavailable'}",
        summary=(
            f"The published question uses the {baseline_date} baseline and {target_date} target under a locked {rule.get('mode')} rule. "
            f"Current source observations are available through {latest_observation_date or 'no supplied date'}; this research does not assert a market outcome."
        ),
        observed_signals=observed_claims[:5],
        notable_changes=[],
        uncertainty=[
            EvidenceClaim("No calibrated probability is produced by this research brief.", ClaimKind.UNKNOWN.value, []),
            EvidenceClaim("The supplied pageview observations do not explain why attention changed.", ClaimKind.UNKNOWN.value, []),
        ],
        missing_evidence=list(dict.fromkeys(missing))[:8],
        suggested_research_questions=[
            "What independent source could explain the observed attention change?",
            "Will the rule's full baseline and target UTC days be available before resolution?",
            "Which assumptions should be checked before staking?",
        ],
        supporting_up=supporting_up,
        supporting_down=supporting_down,
        key_assumptions=assumptions,
        historical_context=historical_claims,
    )
    payload = {
        "brief_type": BriefType.MARKET.value,
        "research_mode": True,
        "market_id": market_id,
        "topic": topic,
        "rule": _research_rule_payload(rule),
        "rule_record": {
            "rule_hash": rule_record.get("rule_hash"),
            "status": rule_record.get("status"),
            "created_at": rule_record.get("created_at"),
        },
        "evidence": _research_evidence_payload(evidence, market_id),
        "attention_observations": payload_observations,
        "historical_context": historical_payload,
        "resolution": resolution.to_dict(),
        "measurement_window": measurement_window,
        "data_as_of": data_as_of,
        "source_ids": [ref.ref_id for ref in refs],
    }
    allowed_numbers, allowed_dates = _allowed_numbers(payload)
    return BriefContext(
        brief_type=BriefType.MARKET.value,
        topic=topic,
        candidate_id=_first_candidate_id(rule),
        market_id=market_id,
        measurement_window=measurement_window,
        data_as_of=data_as_of,
        evidence_references=refs,
        allowed_numbers=allowed_numbers,
        allowed_dates=allowed_dates,
        prompt_payload=payload,
        fallback=fallback,
        resolution=resolution,
        input_digest=_input_digest(payload, "market-research"),
        research_fields_required=True,
    )


def _resolution_explanation(rule: dict[str, Any], evidence: dict[str, Any]) -> ResolutionExplanation:
    observation = rule.get("observation") or {}
    calculation = evidence.get("calculation") or {}
    mode = str(rule.get("mode"))
    formula = rule.get("formula") or {}
    if mode == "trend_trading":
        topic = (rule.get("topics") or [{}])[0].get("article_title") or "the topic"
        text = (
            f"The frozen rule uses full UTC-day pageviews for {topic} on "
            f"{observation.get('baseline_date')} (baseline) and {observation.get('target_date')} "
            f"(target). Growth is floor((target - baseline) * 10000 / baseline). The evidence "
            f"records {_fmt(calculation.get('baseline_views'))} baseline views, "
            f"{_fmt(calculation.get('target_views'))} target views, and "
            f"{_fmt(calculation.get('growth_bps'))} bps growth. Because growth is at least the "
            f"frozen {_fmt(calculation.get('threshold_bps'))} bps threshold, the recorded outcome "
            f"is {evidence.get('outcome')}."
        )
        formula_text = (
            "growth_bps = floor((target_views - baseline_views) * 10000 / baseline_views); "
            f"UP if growth_bps >= {_fmt(formula.get('threshold_bps'))}; otherwise DOWN."
        )
    else:
        topics = rule.get("topics") or []
        a = topics[0].get("article_title") if topics else "topic A"
        b = topics[1].get("article_title") if len(topics) > 1 else "topic B"
        text = (
            f"The frozen rule compares normalized Wikimedia pageview growth for {a} and {b} "
            f"between {observation.get('baseline_date')} and {observation.get('target_date')}. "
            f"Difference is growth_a - growth_b. The evidence records {a} at "
            f"{_fmt(calculation.get('growth_a_bps'))} bps, {b} at "
            f"{_fmt(calculation.get('growth_b_bps'))} bps, a difference of "
            f"{_fmt(calculation.get('difference_bps'))} bps. Because the absolute difference "
            f"exceeds the {_fmt(calculation.get('tie_tolerance_bps'))} bps tie tolerance, the "
            f"recorded outcome is {evidence.get('outcome')}."
        )
        formula_text = (
            "difference_bps = growth_a_bps - growth_b_bps; "
            f"if abs(difference_bps) <= {_fmt(formula.get('tie_tolerance_bps'))} then VOID; "
            "otherwise the higher growth topic wins."
        )
    return ResolutionExplanation(
        rule_hash=str(rule.get("rule_hash") or evidence.get("rule_hash") or ""),
        evidence_digest=str(evidence.get("evidence_digest") or ""),
        mode=mode,
        outcome=str(evidence.get("outcome")),
        text=text,
        formula=formula_text,
        observation_window={
            "baseline_date": observation.get("baseline_date"),
            "target_date": observation.get("target_date"),
            "baseline_window_utc": observation.get("baseline_window_utc"),
            "target_window_utc": observation.get("target_window_utc"),
        },
    )


def _first_candidate_id(rule: dict[str, Any]) -> str | None:
    candidate = rule.get("candidate") or {}
    ids = candidate.get("candidate_ids") or []
    return str(ids[0]) if ids else None


def _claim(text: str, refs: list[str]) -> EvidenceClaim:
    return EvidenceClaim(text=text, kind=ClaimKind.FACT.value, evidence_refs=list(refs))


def _fmt(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _allowed_numbers(payload: Any) -> tuple[set[str], set[str]]:
    numbers: set[str] = set()
    dates: set[str] = set()

    def add_number(value: Any, key: str = "") -> None:
        if isinstance(value, bool) or value is None:
            return
        if any(part in key.lower() for part in ("hash", "url", "ref_id", "source_id", "source_query")):
            return
        if isinstance(value, int):
            numbers.add(str(value))
            numbers.add(f"{value:,}")
            if "bps" in key:
                numbers.add(f"{value / 100:.2f}")
                numbers.add(f"{value / 100:.2f}".rstrip("0").rstrip("."))
        elif isinstance(value, float):
            text = f"{value:g}"
            numbers.add(text)
            if "bps" in key:
                numbers.add(f"{value / 100:.2f}")
                numbers.add(f"{value / 100:.2f}".rstrip("0").rstrip("."))
        elif isinstance(value, str):
            for match in DATE_RE.findall(value):
                dates.add(match)
                dates.add(match[:4])
                numbers.add(match[:4])
            for match in NUMBER_RE.findall(value):
                normalized = match.replace(",", "")
                numbers.add(normalized)
                try:
                    numeric = float(normalized)
                    if numeric.is_integer():
                        numbers.add(str(int(numeric)))
                except ValueError:
                    pass

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        else:
            add_number(value, key)

    walk(payload)
    # Keep the allowed set useful but bounded; the prompt is small.
    return numbers, dates


def _input_digest(payload: dict[str, Any], brief_type: str) -> str:
    return "sha256:" + sha256_text(
        canonical_json(
            {
                "prompt_version": PROMPT_VERSION,
                "brief_type": brief_type,
                "payload": payload,
            }
        )
    )
