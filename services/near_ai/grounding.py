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
