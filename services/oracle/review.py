"""Candidate eligibility hardening and correlated-topic review for S3B."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.trend_radar.canonical import normalize_name

from .calibration import CalibrationReport
from .models import REVIEW_SCHEMA, ValidationReport

SENSITIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "death_or_tragedy": (
        "death",
        "deaths",
        "died",
        "killed",
        "murder",
        "suicide",
        "fatal",
        "victim",
        "disaster",
        "earthquake",
        "flood",
        "hurricane",
        "shooting",
        "war",
        "attack",
    ),
    "health_or_private_person": (
        "cancer",
        "illness",
        "hospital",
        "medical",
        "minor",
        "child",
        "school",
    ),
    "political_or_sensitive_current_event": (
        "election",
        "president",
        "prime minister",
        "minister",
        "senator",
        "congress",
        "parliament",
        "protest",
        "policy",
        "immigration",
    ),
}

KNOWN_RELATIONSHIPS: dict[frozenset[str], tuple[str, str, str]] = {
    frozenset({"nvidia", "jensen huang"}): (
        "company_ceo",
        "high",
        "Jensen Huang is Nvidia's CEO; the topics are not independent measurements.",
    ),
    frozenset({"openai", "chatgpt"}): (
        "company_product",
        "high",
        "ChatGPT is an OpenAI product; the topics are structurally linked.",
    ),
    frozenset({"tesla", "elon musk"}): (
        "company_ceo",
        "high",
        "Elon Musk is Tesla's CEO.",
    ),
    frozenset({"ethereum", "vitalik buterin"}): (
        "founder_project",
        "high",
        "Vitalik Buterin is a founder of Ethereum.",
    ),
}

PERSON_NAME_RE = re.compile(r"^[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3}$")
LIST_OR_NAMESPACE_RE = re.compile(
    r"^(list of |deaths in |timeline of |index of |outline of |glossary of |"
    r"special:|wikipedia:|portal:|category:|template:)",
    re.IGNORECASE,
)


class CandidateRepository:
    """Loads S3A live evidence for the shortlist without regenerating it."""

    def __init__(self, evidence_path: str | Path) -> None:
        self.path = str(evidence_path)
        data = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        self.full = {
            str(candidate["candidate_id"]): candidate
            for candidate in data.get("top_candidates_full_evidence", [])
        }
        self.summary = {
            str(candidate["candidate_id"]): candidate
            for candidate in data.get("all_candidates_summary", [])
        }
        self.by_title = {}
        for candidate in [*self.full.values(), *self.summary.values()]:
            self.by_title.setdefault(normalize_name(str(candidate.get("title", ""))), candidate)

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        return self.full.get(candidate_id) or self.summary.get(candidate_id)

    def get_by_title(self, title: str) -> dict[str, Any] | None:
        match = self.by_title.get(normalize_name(title))
        if match:
            return self.get(str(match["candidate_id"])) or match
        return None


def _aliases(candidate: dict[str, Any]) -> set[str]:
    values = {str(candidate.get("title", ""))}
    values.update(str(alias) for alias in candidate.get("aliases", []))
    signals = candidate.get("discovery_signals", {})
    if signals.get("settlement_article"):
        values.add(str(signals["settlement_article"]))
    for identity in candidate.get("source_identities", []):
        for key in ("article_resolved", "article_original", "title", "name", "symbol", "coin_id"):
            if identity.get(key):
                values.add(str(identity[key]))
    return {normalize_name(value) for value in values if normalize_name(value)}


def _known_relationship(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    names = _aliases(a) | _aliases(b)
    for pair, (kind, severity, reason) in KNOWN_RELATIONSHIPS.items():
        if pair.issubset(names):
            return {
                "type": kind,
                "severity": severity,
                "reason": reason,
                "topics": sorted(pair),
            }
    return None


def relationship_flags(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    canonical_a = str(a.get("canonical_topic_id", ""))
    canonical_b = str(b.get("canonical_topic_id", ""))
    article_a = str(a.get("discovery_signals", {}).get("settlement_article", ""))
    article_b = str(b.get("discovery_signals", {}).get("settlement_article", ""))
    if canonical_a and canonical_a == canonical_b:
        flags.append(
            {
                "type": "same_entity",
                "severity": "high",
                "reason": "Both candidates share the same canonical topic identity.",
            }
        )
    elif article_a and article_a == article_b:
        flags.append(
            {
                "type": "same_article",
                "severity": "high",
                "reason": "Both candidates resolve to the same Wikimedia article.",
            }
        )
    else:
        aliases_a = _aliases(a)
        aliases_b = _aliases(b)
        overlap = aliases_a & aliases_b
        if overlap:
            flags.append(
                {
                    "type": "alias_overlap",
                    "severity": "high",
                    "reason": f"Shared normalized aliases: {sorted(overlap)}",
                }
            )
        title_a = normalize_name(str(a.get("title", "")))
        title_b = normalize_name(str(b.get("title", "")))
        if title_a and title_b and title_a != title_b:
            pattern_a = re.compile(rf"(?<![\w]){re.escape(title_a)}(?![\w])")
            pattern_b = re.compile(rf"(?<![\w]){re.escape(title_b)}(?![\w])")
            if pattern_a.search(title_b) or pattern_b.search(title_a):
                flags.append(
                    {
                        "type": "parent_child_topic",
                        "severity": "high",
                        "reason": "One topic title is contained in the other; likely a parent/child topic.",
                    }
                )
    known = _known_relationship(a, b)
    if known:
        flags.append(known)
    return flags


def _measurement_status(calibration: CalibrationReport | None) -> tuple[bool, str]:
    if calibration is None:
        return False, "UNVERIFIED"
    if calibration.status == "OK" and calibration.observation_status in {"AVAILABLE", "PENDING_OBSERVATION"}:
        if calibration.observation_status == "AVAILABLE" and (calibration.baseline_views or 0) < calibration.min_baseline_views:
            return False, "INVALID"
        return True, "VALID" if calibration.observation_status == "AVAILABLE" else "PENDING_OBSERVATION"
    if calibration.observation_status == "PENDING_OBSERVATION" and calibration.status == "OK":
        return True, "PENDING_OBSERVATION"
    return False, "HOLD"


def _market_interest(candidate: dict[str, Any], calibration: CalibrationReport | None) -> tuple[str, list[str]]:
    views = None
    if calibration and calibration.baseline_views is not None:
        views = calibration.baseline_views
    else:
        top_views = [
            evidence.get("metrics", {}).get("views")
            for evidence in candidate.get("discovery_evidence", [])
            if evidence.get("metrics", {}).get("views") is not None
        ]
        views = max(top_views) if top_views else None
    sources = candidate.get("discovery_signals", {}).get("source_count", 1)
    reasons = [f"baseline_or_top_views={views}", f"source_count={sources}"]
    if views is not None and views >= 100_000:
        label = "high"
    elif views is not None and views >= 20_000:
        label = "medium"
    elif views is not None and views >= 1_000:
        label = "low_but_measurable"
    else:
        label = "unknown"
    if sources >= 2:
        reasons.append("multiple_sources")
    return label, reasons


def _sensitivity_flags(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(candidate.get("title", ""))
    article = str(candidate.get("discovery_signals", {}).get("settlement_article", ""))
    text = normalize_name(f"{title} {article}")
    flags = []
    for flag_type, keywords in SENSITIVE_KEYWORDS.items():
        matched = [keyword for keyword in keywords if re.search(rf"(?<![\w]){re.escape(keyword)}(?![\w])", text)]
        if matched:
            flags.append(
                {
                    "type": flag_type,
                    "severity": "review",
                    "reason": f"Matched sensitive terms: {', '.join(sorted(matched))}",
                }
            )
    if PERSON_NAME_RE.fullmatch(title):
        flags.append(
            {
                "type": "person_or_public_individual",
                "severity": "review",
                "reason": "Title looks like a person's name; operator must assess sensitivity and public-figure status.",
            }
        )
    return flags


def _ambiguity(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    title = str(candidate.get("title", ""))
    signals = candidate.get("discovery_signals", {})
    if signals.get("settlement_page_id") is None:
        reasons.append("missing_page_id")
    if "(disambiguation)" in title.casefold():
        reasons.append("disambiguation_title")
    for identity in candidate.get("source_identities", []):
        if identity.get("redirected_from"):
            reasons.append(f"redirected_from:{identity['redirected_from']}")
    if LIST_OR_NAMESPACE_RE.search(title):
        reasons.append("list_or_namespace_page")
    return bool(reasons), reasons


def review_candidate(
    candidate: dict[str, Any],
    *,
    calibration: CalibrationReport | None = None,
) -> ValidationReport:
    measurement_valid, measurement_status = _measurement_status(calibration)
    interest, interest_reasons = _market_interest(candidate, calibration)
    ambiguous, ambiguity_reasons = _ambiguity(candidate)
    flags = _sensitivity_flags(candidate)
    reasons = []
    if not measurement_valid:
        reasons.append(f"measurement_{measurement_status.lower()}")
    if ambiguous:
        reasons.append("ambiguous_article_mapping")
    if flags:
        reasons.append("sensitive_topic_review")
    if ambiguous or flags:
        recommendation = "HOLD_FOR_OPERATOR_REVIEW"
    elif measurement_status == "PENDING_OBSERVATION":
        recommendation = "READY_FOR_OPERATOR_REVIEW_FUTURE"
    elif measurement_valid:
        recommendation = "READY_FOR_OPERATOR_REVIEW"
    else:
        recommendation = "HOLD_FOR_CALIBRATION"
    if not candidate.get("discovery_signals", {}).get("settlement_article"):
        recommendation = "REJECT_NOT_MEASURABLE"
        reasons.append("no_settlement_article")
    return ValidationReport(
        schema_version=REVIEW_SCHEMA,
        candidate_ids=[str(candidate.get("candidate_id"))],
        title=str(candidate.get("title")),
        canonical_topic_ids=[str(candidate.get("canonical_topic_id"))],
        category=candidate.get("category"),
        measurement_valid=measurement_valid,
        measurement_status=measurement_status,
        market_interest=interest,
        market_interest_reasons=interest_reasons,
        recognizable_topic=not ambiguous and bool(candidate.get("discovery_signals", {}).get("settlement_page_id")),
        recognizable_reasons=[] if not ambiguous else ambiguity_reasons,
        sensitivity_flags=flags,
        relationship_flags=[],
        ambiguous_mapping=ambiguous,
        ambiguity_reasons=ambiguity_reasons,
        operator_approval_required=True,
        recommendation=recommendation,
        reasons=reasons,
        sources=[
            {
                "source": identity.get("source"),
                "source_id": identity.get("source_id"),
                "url": identity.get("url"),
            }
            for identity in candidate.get("source_identities", [])
        ],
    )


def review_battle_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    calibration: CalibrationReport | None = None,
) -> ValidationReport:
    flags = relationship_flags(a, b)
    review_a = review_candidate(a, calibration=calibration)
    review_b = review_candidate(b, calibration=calibration)
    reasons = []
    if not review_a.measurement_valid or not review_b.measurement_valid:
        reasons.append("both_topics_must_be_measurement_valid")
    if flags:
        reasons.append("correlated_or_same_entity_topics")
    if flags and any(flag.get("severity") == "high" for flag in flags):
        recommendation = "REJECT_CORRELATED_TOPICS"
    elif reasons:
        recommendation = "HOLD_FOR_OPERATOR_REVIEW"
    else:
        recommendation = "READY_FOR_OPERATOR_REVIEW"
    return ValidationReport(
        schema_version=REVIEW_SCHEMA,
        candidate_ids=[str(a.get("candidate_id")), str(b.get("candidate_id"))],
        title=f"{a.get('title')} vs {b.get('title')}",
        canonical_topic_ids=[
            str(a.get("canonical_topic_id")),
            str(b.get("canonical_topic_id")),
        ],
        category=a.get("category") if a.get("category") == b.get("category") else None,
        measurement_valid=review_a.measurement_valid and review_b.measurement_valid,
        measurement_status=(
            "VALID" if review_a.measurement_valid and review_b.measurement_valid else "HOLD"
        ),
        market_interest=review_a.market_interest,
        market_interest_reasons=(
            review_a.market_interest_reasons + review_b.market_interest_reasons
        ),
        recognizable_topic=review_a.recognizable_topic and review_b.recognizable_topic,
        recognizable_reasons=review_a.recognizable_reasons + review_b.recognizable_reasons,
        sensitivity_flags=review_a.sensitivity_flags + review_b.sensitivity_flags,
        relationship_flags=flags,
        ambiguous_mapping=review_a.ambiguous_mapping or review_b.ambiguous_mapping,
        ambiguity_reasons=review_a.ambiguity_reasons + review_b.ambiguity_reasons,
        operator_approval_required=True,
        recommendation=recommendation,
        reasons=reasons,
        sources=review_a.sources + review_b.sources,
    )
