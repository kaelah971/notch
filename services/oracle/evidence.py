"""Canonical evidence receipts and independent verification."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.models import iso_utc, jsonable

from .calculations import (
    CalculationError,
    battle_calculation,
    trend_calculation,
)
from .models import EVIDENCE_SCHEMA, RESOLVER_VERSION, Evidence, PageviewsRange
from .rules import rule_digest, validate_rule
from .wikimedia import observation_hash

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class EvidenceError(ValueError):
    pass


def _invalid_reason(
    range_result: PageviewsRange | None,
    baseline: dict[str, Any] | None,
    target: dict[str, Any] | None,
    min_baseline_views: int,
) -> str | None:
    if range_result is None:
        return "source_range_missing"
    if range_result.error:
        return "source_retrieval_error"
    if range_result.missing_dates:
        return "missing_source_observations"
    if range_result.duplicate_dates:
        return "duplicate_source_observations"
    if baseline is None:
        return "missing_baseline_observation"
    if target is None:
        return "missing_target_observation"
    if baseline["views"] < min_baseline_views:
        return "baseline_below_minimum"
    return None


def _observation_record(observation, source_query: str) -> dict[str, Any]:
    return {
        "date": observation.date,
        "views": observation.views,
        "source_timestamp": observation.timestamp,
        "project": observation.project,
        "article": observation.article,
        "access": observation.access,
        "agent": observation.agent,
        "retrieved_at": iso_utc(observation.retrieved_at),
        "source_url": observation.source_url,
        "source_query": source_query,
        "raw_response_hash": observation.raw_response_hash,
        "observation_hash": observation.observation_hash,
    }


def _range_for(ranges: dict[str, PageviewsRange], article: str) -> PageviewsRange | None:
    if article in ranges:
        return ranges[article]
    normalized = article.casefold()
    for key, value in ranges.items():
        if key.casefold() == normalized:
            return value
    return None


def build_evidence(
    rule: dict[str, Any],
    ranges: dict[str, PageviewsRange],
    *,
    retrieved_at: str | None = None,
) -> Evidence:
    errors = validate_rule(rule)
    if errors:
        raise EvidenceError("invalid rule: " + ", ".join(errors))
    rule_hash = rule_digest(rule)
    baseline_date = rule["observation"]["baseline_date"]
    target_date = rule["observation"]["target_date"]
    min_baseline = int(rule["minimum_baseline_views"])
    observations: dict[str, dict[str, Any]] = {}
    raw_hashes: list[str] = []
    retrieved_values: list[str] = []
    invalid_reasons: list[str] = []

    for topic in rule["topics"]:
        article = topic["article_title"]
        range_result = _range_for(ranges, article)
        baseline = target = None
        if range_result is not None:
            baseline_obs = range_result.observations.get(baseline_date)
            target_obs = range_result.observations.get(target_date)
            baseline = _observation_record(baseline_obs, range_result.source_url) if baseline_obs else None
            target = _observation_record(target_obs, range_result.source_url) if target_obs else None
            if range_result.raw_response_hash:
                raw_hashes.append(range_result.raw_response_hash)
            if range_result.retrieved_at:
                retrieved_values.append(iso_utc(range_result.retrieved_at))
        reason = _invalid_reason(range_result, baseline, target, min_baseline)
        if reason:
            invalid_reasons.append(reason)
        topic_key = topic["topic_id"]
        observations[topic_key] = {
            "article": article,
            "page_id": topic.get("page_id"),
            "baseline": baseline,
            "target": target,
            "range": {
                "source_url": range_result.source_url if range_result else None,
                "start_date": range_result.start_date if range_result else None,
                "end_date": range_result.end_date if range_result else None,
                "raw_response_hash": range_result.raw_response_hash if range_result else None,
                "retrieved_at": iso_utc(range_result.retrieved_at) if range_result and range_result.retrieved_at else None,
            },
        }

    if rule["mode"] == "trend_trading":
        topic_key = rule["topics"][0]["topic_id"]
        obs = observations[topic_key]
        if invalid_reasons:
            calculation = {
                "outcome": "INVALID",
                "invalidity_reason": invalid_reasons[0],
                "baseline_views": obs["baseline"]["views"] if obs["baseline"] else None,
                "target_views": obs["target"]["views"] if obs["target"] else None,
                "growth_bps": None,
                "threshold_bps": rule["formula"]["threshold_bps"],
            }
        else:
            calculation = trend_calculation(
                obs["baseline"]["views"],
                obs["target"]["views"],
                rule["formula"]["threshold_bps"],
                min_baseline,
            )
    else:
        topic_a = rule["topics"][0]
        topic_b = rule["topics"][1]
        obs_a = observations[topic_a["topic_id"]]
        obs_b = observations[topic_b["topic_id"]]
        if invalid_reasons:
            calculation = {
                "outcome": "INVALID",
                "invalidity_reason": invalid_reasons[0],
                "baseline_a": obs_a["baseline"]["views"] if obs_a["baseline"] else None,
                "target_a": obs_a["target"]["views"] if obs_a["target"] else None,
                "baseline_b": obs_b["baseline"]["views"] if obs_b["baseline"] else None,
                "target_b": obs_b["target"]["views"] if obs_b["target"] else None,
                "growth_a_bps": None,
                "growth_b_bps": None,
                "difference_bps": None,
                "tie_tolerance_bps": rule["formula"]["tie_tolerance_bps"],
            }
        else:
            calculation = battle_calculation(
                obs_a["baseline"]["views"],
                obs_a["target"]["views"],
                obs_b["baseline"]["views"],
                obs_b["target"]["views"],
                rule["formula"]["tie_tolerance_bps"],
                min_baseline,
            )

    outcome = calculation["outcome"]
    invalidity = calculation.get("invalidity_reason") if outcome == "INVALID" else None
    evidence = Evidence(
        schema_version=EVIDENCE_SCHEMA,
        market_id=rule["market_id"],
        rule_hash=rule_hash,
        mode=rule["mode"],
        resolver_version=RESOLVER_VERSION,
        source=rule["source"],
        topics=rule["topics"],
        observation=rule["observation"],
        observations=observations,
        calculation=calculation,
        outcome=outcome,
        invalidity_reason=invalidity,
        retrieved_at=retrieved_at or (max(retrieved_values) if retrieved_values else ""),
        raw_source_hashes=sorted(set(raw_hashes)),
        integrity_note=(
            "The evidence digest proves the integrity of the recorded source "
            "payload hashes and calculation inputs. It does not prove that "
            "Wikimedia pageviews are organic, complete or free of manipulation."
        ),
        evidence_digest="",
    )
    evidence.calculation.setdefault("minimum_baseline_views", min_baseline)
    evidence.evidence_digest = evidence_digest(evidence)
    return evidence


def _strip_retrieval_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove wall-clock retrieval metadata from the digest payload.

    Retrieval timestamps are preserved in the receipt but are not source
    measurements. Excluding them lets the same historical data reproduce the
    same digest on a later fetch.
    """
    import copy

    payload = copy.deepcopy(payload)
    payload.pop("retrieved_at", None)
    for entry in (payload.get("observations") or {}).values():
        for side in ("baseline", "target"):
            observation = entry.get(side)
            if isinstance(observation, dict):
                observation.pop("retrieved_at", None)
        range_info = entry.get("range")
        if isinstance(range_info, dict):
            range_info.pop("retrieved_at", None)
    return payload


def evidence_payload(evidence: Evidence | dict[str, Any]) -> dict[str, Any]:
    payload = jsonable(evidence)
    payload.pop("evidence_digest", None)
    return _strip_retrieval_metadata(payload)


def evidence_digest(evidence: Evidence | dict[str, Any]) -> str:
    return "sha256:" + sha256_text(canonical_json(evidence_payload(evidence)))


def evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    return jsonable(evidence)


def save_evidence(evidence: Evidence, output_dir: str | Path) -> Path:
    payload = evidence_to_dict(evidence)
    if not DIGEST_RE.fullmatch(evidence.evidence_digest):
        raise EvidenceError("invalid evidence digest format")
    path = Path(output_dir) / f"{evidence.market_id}.{evidence.evidence_digest.split(':', 1)[1]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _recompute_calculation(doc: dict[str, Any]) -> dict[str, Any]:
    calculation = doc.get("calculation") or {}
    mode = doc.get("mode")
    try:
        if mode == "trend_trading":
            topic = doc["topics"][0]
            obs = doc["observations"][topic["topic_id"]]
            baseline = obs["baseline"]
            target = obs["target"]
            if baseline is None or target is None:
                return {"ok": False, "reason": "missing_observation"}
            return {
                "ok": True,
                "recomputed": trend_calculation(
                    int(baseline["views"]),
                    int(target["views"]),
                    int(calculation["threshold_bps"]),
                    int(calculation.get("minimum_baseline_views", doc.get("minimum_baseline_views", 1000))),
                ),
            }
        if mode == "trend_battle":
            obs_a = doc["observations"][doc["topics"][0]["topic_id"]]
            obs_b = doc["observations"][doc["topics"][1]["topic_id"]]
            if (
                obs_a["baseline"] is None
                or obs_a["target"] is None
                or obs_b["baseline"] is None
                or obs_b["target"] is None
            ):
                return {"ok": False, "reason": "missing_observation"}
            return {
                "ok": True,
                "recomputed": battle_calculation(
                    int(obs_a["baseline"]["views"]),
                    int(obs_a["target"]["views"]),
                    int(obs_b["baseline"]["views"]),
                    int(obs_b["target"]["views"]),
                    int(calculation["tie_tolerance_bps"]),
                    int(calculation.get("minimum_baseline_views", doc.get("minimum_baseline_views", 1000))),
                ),
            }
    except (CalculationError, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "reason": f"calculation_input_error: {exc}"}
    return {"ok": False, "reason": "unknown_mode"}


def verify_evidence(
    doc: dict[str, Any],
    *,
    expected_rule_hash: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if doc.get("schema_version") != EVIDENCE_SCHEMA:
        reasons.append("invalid_schema_version")
    digest = str(doc.get("evidence_digest", ""))
    if not DIGEST_RE.fullmatch(digest):
        reasons.append("invalid_digest_format")
    recomputed = evidence_digest(doc)
    if digest != recomputed:
        reasons.append("digest_mismatch")
    if expected_rule_hash and doc.get("rule_hash") != expected_rule_hash:
        reasons.append("rule_hash_mismatch")
    if not DIGEST_RE.fullmatch(str(doc.get("rule_hash", ""))):
        reasons.append("invalid_rule_hash")
    observations = doc.get("observations") or {}
    for topic in doc.get("topics") or []:
        entry = observations.get(topic.get("topic_id"))
        if not entry:
            reasons.append(f"missing_topic_evidence:{topic.get('topic_id')}")
            continue
        for side in ("baseline", "target"):
            observation = entry.get(side)
            if observation is None:
                continue
            expected_observation_hash = observation_hash(
                type(
                    "Obs",
                    (),
                    {
                        "date": observation.get("date"),
                        "views": observation.get("views"),
                        "timestamp": observation.get("source_timestamp"),
                    },
                )()
            )
            if observation.get("observation_hash") != expected_observation_hash:
                reasons.append(f"observation_hash_mismatch:{topic.get('topic_id')}:{side}")
    calculation = doc.get("calculation") or {}
    outcome = calculation.get("outcome")
    if outcome == "INVALID":
        if not calculation.get("invalidity_reason"):
            reasons.append("invalid_outcome_without_reason")
    else:
        recompute = _recompute_calculation(doc)
        if not recompute.get("ok"):
            reasons.append(recompute.get("reason", "calculation_recompute_failed"))
        else:
            recomputed_outcome = recompute["recomputed"].get("outcome")
            if recomputed_outcome != outcome:
                reasons.append("outcome_mismatch")
    if not doc.get("raw_source_hashes"):
        reasons.append("missing_raw_source_hashes")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "evidence_digest": recomputed,
        "outcome": outcome,
        "rule_hash": doc.get("rule_hash"),
        "integrity_note": doc.get("integrity_note"),
    }
