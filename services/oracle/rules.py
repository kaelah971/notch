"""Versioned canonical market rules and exact S2 contract arguments."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from services.trend_radar.canonical import canonical_json, normalize_name, sha256_text, slugify
from services.trend_radar.models import iso_utc, jsonable, parse_iso

from .models import RULE_SCHEMA

DEFAULT_MIN_BASELINE_VIEWS = 1000
DEFAULT_THRESHOLD_BPS = 1500
DEFAULT_TIE_TOLERANCE_BPS = 50
MIN_ENTRY_CLOSE_AHEAD_DAYS = 1
DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
MARKET_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
TITLE_OR_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RuleValidationError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    return iso_utc(value)


def to_ns(value: datetime) -> int:
    return int(value.timestamp()) * 1_000_000_000


def ns_to_iso(value: int | str) -> str:
    return iso_utc(datetime.fromtimestamp(int(value) / 1e9, tz=timezone.utc))


def day_start(day: date) -> datetime:
    return datetime.combine(day, time(0, 0, 0), tzinfo=timezone.utc)


def day_end(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)


def topic_id_for(candidate: dict[str, Any]) -> str:
    canonical = str(candidate.get("canonical_topic_id", ""))
    if canonical.startswith("entity:"):
        return slugify(canonical.split(":", 1)[1])
    return slugify(str(candidate.get("title", "topic")))


def article_for(candidate: dict[str, Any]) -> str:
    article = candidate.get("discovery_signals", {}).get("settlement_article")
    if not article:
        raise RuleValidationError("candidate has no settlement article")
    return str(article)


def page_id_for(candidate: dict[str, Any]) -> int | None:
    page_id = candidate.get("discovery_signals", {}).get("settlement_page_id")
    return int(page_id) if page_id is not None else None


def source_for(article: str) -> dict[str, Any]:
    return {
        "id": "wikimedia-pageviews-v1",
        "provider": "Wikimedia Analytics API",
        "project": "en.wikipedia.org",
        "access": "all-access",
        "agent": "user",
        "metric": "daily_pageviews",
        "granularity": "daily",
        "timezone": "UTC",
        "article": article,
        "documentation": (
            "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/"
            "documentation/getting-started.html"
        ),
    }


def observation_window(
    baseline_date: date, target_date: date, replay: bool
) -> dict[str, Any]:
    return {
        "baseline_date": baseline_date.isoformat(),
        "target_date": target_date.isoformat(),
        "baseline_window_utc": (
            f"{baseline_date.isoformat()}T00:00:00Z/"
            f"{baseline_date.isoformat()}T23:59:59Z"
        ),
        "target_window_utc": (
            f"{target_date.isoformat()}T00:00:00Z/"
            f"{target_date.isoformat()}T23:59:59Z"
        ),
        "replay": bool(replay),
        "replay_label": "HISTORICAL_REPLAY" if replay else None,
    }


def market_timing(
    *,
    open_at: datetime,
    close_at: datetime,
    resolve_after: datetime,
) -> dict[str, Any]:
    return {
        "open_at_ns": str(to_ns(open_at)),
        "close_at_ns": str(to_ns(close_at)),
        "resolve_after_ns": str(to_ns(resolve_after)),
        "open_at_utc": iso_z(open_at),
        "close_at_utc": iso_z(close_at),
        "resolve_after_utc": iso_z(resolve_after),
    }


def default_future_timing(now: datetime) -> dict[str, Any]:
    """Entry/observation timing for a prospective future market."""
    open_at = now + timedelta(hours=1)
    close_at = datetime.combine(
        (now + timedelta(days=3)).date(), time(23, 59, 0), tzinfo=timezone.utc
    )
    baseline = close_at.date() + timedelta(days=1)
    target = baseline + timedelta(days=7)
    resolve_after = datetime.combine(
        target + timedelta(days=2), time(12, 0, 0), tzinfo=timezone.utc
    )
    return {
        "market_timing": market_timing(
            open_at=open_at, close_at=close_at, resolve_after=resolve_after
        ),
        "baseline_date": baseline,
        "target_date": target,
    }


def replay_timing(now: datetime, *, baseline_date: date, target_date: date) -> dict[str, Any]:
    """Future contract entry/close for a historical observation window."""
    open_at = now + timedelta(hours=1)
    close_at = datetime.combine(
        (now + timedelta(days=3)).date(), time(23, 59, 0), tzinfo=timezone.utc
    )
    resolve_after = datetime.combine(
        (now + timedelta(days=5)).date(), time(12, 0, 0), tzinfo=timezone.utc
    )
    if resolve_after <= day_end(target_date):
        raise RuleValidationError("replay resolve_after must be after the target day")
    if resolve_after <= close_at:
        raise RuleValidationError("replay resolve_after must be after entry close")
    return {
        "market_timing": market_timing(
            open_at=open_at, close_at=close_at, resolve_after=resolve_after
        ),
        "baseline_date": baseline_date,
        "target_date": target_date,
    }


def _candidate_metadata(candidate: dict[str, Any], proposal_refs: list[str], review: dict | None) -> dict[str, Any]:
    return {
        "candidate_ids": [str(candidate.get("candidate_id"))],
        "canonical_topic_ids": [str(candidate.get("canonical_topic_id"))],
        "source_proposal_refs": list(proposal_refs),
        "validation_status": (review or {}).get("recommendation", "READY_FOR_OPERATOR_REVIEW"),
        "operator_approval_required": True,
    }


def build_trend_rule(
    *,
    candidate: dict[str, Any],
    baseline_date: date,
    target_date: date,
    threshold_bps: int,
    min_baseline_views: int,
    timing: dict[str, Any],
    calibration_report: dict[str, Any],
    contract: dict[str, Any],
    replay: bool,
    question: str,
    proposal_refs: list[str] | None = None,
    review: dict | None = None,
) -> dict[str, Any]:
    article = article_for(candidate)
    return {
        "schema_version": RULE_SCHEMA,
        "rule_version": "s3b-oracle/1",
        "market_id": str(timing["market_id"]),
        "mode": "trend_trading",
        "question": question,
        "choices": ["UP", "DOWN"],
        "source": source_for(article),
        "topics": [
            {
                "topic_id": topic_id_for(candidate),
                "article_title": article,
                "page_id": page_id_for(candidate),
                "source_url": f"https://en.wikipedia.org/wiki/{article.replace(' ', '_')}",
            }
        ],
        "observation": observation_window(baseline_date, target_date, replay),
        "formula": {
            "version": "growth-threshold-v1",
            "growth_bps": "floor((target_views - baseline_views) * 10000 / baseline_views)",
            "threshold_bps": int(threshold_bps),
            "up_if": "growth_bps >= threshold_bps",
            "down_if": "growth_bps < threshold_bps",
            "integer_only": True,
            "rounding": "mathematical floor; negative numerators floor below zero",
        },
        "minimum_baseline_views": int(min_baseline_views),
        "invalidation_policy": "refund_on_void",
        "missing_data_policy": "void",
        "resolution_eligibility_utc": timing["market_timing"]["resolve_after_utc"],
        "market_timing": timing["market_timing"],
        "contract": dict(contract),
        "candidate": _candidate_metadata(candidate, proposal_refs or [], review),
        "calibration": {
            "report_digest": calibration_report.get("report_digest"),
            "suggested_threshold_bps": calibration_report.get("suggested_threshold_bps"),
            "policy": calibration_report.get("threshold_policy"),
            "calibration_window": {
                "start": calibration_report.get("calibration_start"),
                "end": calibration_report.get("calibration_end"),
            },
            "status": calibration_report.get("status"),
        },
        "governance": {
            "status": "READY_FOR_OPERATOR_REVIEW",
            "operator_approval_required": True,
            "auto_approved": False,
        },
    }


def build_battle_rule(
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    baseline_date: date,
    target_date: date,
    tie_tolerance_bps: int,
    min_baseline_views: int,
    timing: dict[str, Any],
    calibration_report: dict[str, Any],
    contract: dict[str, Any],
    replay: bool,
    question: str,
    proposal_refs: list[str] | None = None,
    review: dict | None = None,
) -> dict[str, Any]:
    article_a = article_for(candidate_a)
    article_b = article_for(candidate_b)
    source = source_for(article_a)
    return {
        "schema_version": RULE_SCHEMA,
        "rule_version": "s3b-oracle/1",
        "market_id": str(timing["market_id"]),
        "mode": "trend_battle",
        "question": question,
        "choices": [str(candidate_a.get("title")), str(candidate_b.get("title"))],
        "source": {**source, "metric": "daily_pageviews_growth_comparison"},
        "topics": [
            {
                "topic_id": topic_id_for(candidate_a),
                "article_title": article_a,
                "page_id": page_id_for(candidate_a),
                "source_url": f"https://en.wikipedia.org/wiki/{article_a.replace(' ', '_')}",
            },
            {
                "topic_id": topic_id_for(candidate_b),
                "article_title": article_b,
                "page_id": page_id_for(candidate_b),
                "source_url": f"https://en.wikipedia.org/wiki/{article_b.replace(' ', '_')}",
            },
        ],
        "observation": observation_window(baseline_date, target_date, replay),
        "formula": {
            "version": "growth_comparison_v1",
            "growth_bps": "floor((target_views - baseline_views) * 10000 / baseline_views)",
            "comparison": "difference_bps = growth_a_bps - growth_b_bps",
            "tie_tolerance_bps": int(tie_tolerance_bps),
            "tie_policy": "void",
            "tie_if": "abs(difference_bps) <= tie_tolerance_bps",
            "winner_if": "abs(difference_bps) > tie_tolerance_bps",
            "integer_only": True,
        },
        "minimum_baseline_views": int(min_baseline_views),
        "invalidation_policy": "refund_on_void",
        "missing_data_policy": "void",
        "resolution_eligibility_utc": timing["market_timing"]["resolve_after_utc"],
        "market_timing": timing["market_timing"],
        "contract": dict(contract),
        "candidate": {
            "candidate_ids": [
                str(candidate_a.get("candidate_id")),
                str(candidate_b.get("candidate_id")),
            ],
            "canonical_topic_ids": [
                str(candidate_a.get("canonical_topic_id")),
                str(candidate_b.get("canonical_topic_id")),
            ],
            "source_proposal_refs": list(proposal_refs or []),
            "validation_status": (review or {}).get("recommendation", "READY_FOR_OPERATOR_REVIEW"),
            "operator_approval_required": True,
        },
        "calibration": {
            "report_digest": calibration_report.get("report_digest"),
            "suggested_tie_tolerance_bps": calibration_report.get("suggested_tie_tolerance_bps"),
            "policy": calibration_report.get("tie_policy"),
            "calibration_window": {
                "start": calibration_report.get("calibration_start"),
                "end": calibration_report.get("calibration_end"),
            },
            "status": calibration_report.get("status"),
        },
        "governance": {
            "status": "READY_FOR_OPERATOR_REVIEW",
            "operator_approval_required": True,
            "auto_approved": False,
        },
    }


def rule_digest(rule: dict[str, Any]) -> str:
    return "sha256:" + sha256_text(canonical_json(rule))


def validate_rule(rule: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    errors: list[str] = []
    if rule.get("schema_version") != RULE_SCHEMA:
        errors.append("invalid_schema_version")
    market_id = str(rule.get("market_id", ""))
    if not MARKET_ID_RE.fullmatch(market_id):
        errors.append("invalid_market_id")
    mode = rule.get("mode")
    if mode not in {"trend_trading", "trend_battle"}:
        errors.append("invalid_mode")
    question = str(rule.get("question", ""))
    if not question.strip() or len(question.encode("utf-8")) > 500:
        errors.append("invalid_question")
    choices = rule.get("choices")
    if not isinstance(choices, list) or len(choices) != 2:
        errors.append("invalid_choices")
    elif not all(isinstance(c, str) and 0 < len(c) <= 64 for c in choices):
        errors.append("invalid_choices")
    elif choices[0] == choices[1]:
        errors.append("invalid_choices")
    source = rule.get("source") or {}
    if source.get("id") != "wikimedia-pageviews-v1":
        errors.append("invalid_source")
    if source.get("project") != "en.wikipedia.org" or source.get("access") != "all-access" or source.get("agent") != "user":
        errors.append("invalid_source_query")
    topics = rule.get("topics") or []
    expected_topics = 2 if mode == "trend_battle" else 1
    if not isinstance(topics, list) or len(topics) != expected_topics:
        errors.append("invalid_topics")
    for topic in topics if isinstance(topics, list) else []:
        if not SLUG_RE.fullmatch(str(topic.get("topic_id", ""))):
            errors.append("invalid_topic_id")
        if not topic.get("article_title"):
            errors.append("invalid_article_title")
        if topic.get("page_id") is None:
            errors.append("missing_page_id")
    if mode == "trend_battle" and len(topics) == 2:
        if topics[0].get("topic_id") == topics[1].get("topic_id"):
            errors.append("topics_not_distinct")
        if topics[0].get("article_title") == topics[1].get("article_title"):
            errors.append("topics_not_distinct")
    observation = rule.get("observation") or {}
    try:
        baseline = date.fromisoformat(observation.get("baseline_date", ""))
        target = date.fromisoformat(observation.get("target_date", ""))
    except ValueError:
        errors.append("invalid_observation_dates")
        baseline = target = None
    replay = bool(observation.get("replay"))
    if baseline and target:
        if baseline >= target:
            errors.append("invalid_observation_dates")
        if replay and observation.get("replay_label") != "HISTORICAL_REPLAY":
            errors.append("invalid_replay_label")
        if replay and not question.startswith("HISTORICAL REPLAY"):
            errors.append("replay_question_must_be_labeled")
        if not replay and not question.startswith("FORECAST"):
            errors.append("future_question_must_be_labeled")
    formula = rule.get("formula") or {}
    if mode == "trend_trading":
        if formula.get("version") != "growth-threshold-v1":
            errors.append("invalid_formula")
        threshold = formula.get("threshold_bps")
        if not isinstance(threshold, int) or not 0 <= threshold <= 1_000_000:
            errors.append("invalid_threshold")
    elif mode == "trend_battle":
        if formula.get("version") != "growth_comparison_v1":
            errors.append("invalid_formula")
        tolerance = formula.get("tie_tolerance_bps")
        if not isinstance(tolerance, int) or not 0 <= tolerance <= 10000:
            errors.append("invalid_tie_tolerance")
        if formula.get("tie_policy") != "void":
            errors.append("invalid_tie_policy")
    if not isinstance(rule.get("minimum_baseline_views"), int) or rule["minimum_baseline_views"] <= 0:
        errors.append("invalid_min_baseline")
    if rule.get("invalidation_policy") != "refund_on_void":
        errors.append("invalid_invalidation_policy")
    timing = rule.get("market_timing") or {}
    try:
        open_ns = int(timing["open_at_ns"])
        close_ns = int(timing["close_at_ns"])
        resolve_ns = int(timing["resolve_after_ns"])
    except (KeyError, TypeError, ValueError):
        errors.append("invalid_market_timing")
        open_ns = close_ns = resolve_ns = 0
    if not (0 < open_ns < close_ns <= resolve_ns):
        errors.append("invalid_market_timing")
    for ns_key, iso_key in (
        ("open_at_ns", "open_at_utc"),
        ("close_at_ns", "close_at_utc"),
        ("resolve_after_ns", "resolve_after_utc"),
    ):
        try:
            if to_ns(parse_utc(str(timing[iso_key]))) != int(timing[ns_key]):
                errors.append("market_timing_iso_mismatch")
                break
        except (KeyError, TypeError, ValueError):
            errors.append("invalid_market_timing")
            break
    if now is not None and close_ns <= to_ns(now):
        errors.append("entry_close_in_past")
    if baseline and target:
        if resolve_ns < to_ns(day_end(target)):
            errors.append("resolution_before_target_window")
    if mode == "trend_battle" and topics and len(topics) == 2:
        if source.get("metric") != "daily_pageviews_growth_comparison":
            errors.append("invalid_battle_metric")
    contract = rule.get("contract") or {}
    if not contract.get("account") or not contract.get("collateral_token"):
        errors.append("invalid_contract_metadata")
    governance = rule.get("governance") or {}
    if governance.get("operator_approval_required") is not True:
        errors.append("operator_approval_missing")
    if governance.get("auto_approved") is not False:
        errors.append("auto_approval_forbidden")
    return errors


def build_contract_args(rule: dict[str, Any]) -> dict[str, Any]:
    errors = validate_rule(rule)
    if errors:
        raise RuleValidationError(", ".join(errors))
    timing = rule["market_timing"]
    args: dict[str, Any] = {
        "market_id": rule["market_id"],
        "mode": rule["mode"],
        "question": rule["question"],
        "choices": rule["choices"],
        "source_id": rule["source"]["id"],
        "rule_hash": rule_digest(rule),
        "open_at": timing["open_at_ns"],
        "close_at": timing["close_at_ns"],
        "resolve_after": timing["resolve_after_ns"],
        "invalidation_policy": rule["invalidation_policy"],
    }
    if rule["mode"] == "trend_battle":
        topic_a, topic_b = rule["topics"]
        args["battle"] = {
            "topic_a": {
                "topic_id": topic_a["topic_id"],
                "source_id": rule["source"]["id"],
                "project": rule["source"]["project"],
                "article_title": topic_a["article_title"],
                "metric": "daily_pageviews_growth_comparison",
            },
            "topic_b": {
                "topic_id": topic_b["topic_id"],
                "source_id": rule["source"]["id"],
                "project": rule["source"]["project"],
                "article_title": topic_b["article_title"],
                "metric": "daily_pageviews_growth_comparison",
            },
            "observation_start": str(to_ns(day_start(date.fromisoformat(rule["observation"]["baseline_date"])))),
            "observation_end": str(to_ns(day_end(date.fromisoformat(rule["observation"]["target_date"])))),
            "formula": "growth_comparison_v1",
            "min_baseline_views": str(rule["minimum_baseline_views"]),
            "tie_tolerance_bps": rule["formula"]["tie_tolerance_bps"],
            "tie_policy": "void",
        }
    return {"args": args}


def validate_create_args(payload: dict[str, Any]) -> list[str]:
    """Mirror the deployed S2 create_market validation in Python."""
    errors: list[str] = []
    args = payload.get("args")
    if not isinstance(args, dict):
        return ["missing_args"]
    if not MARKET_ID_RE.fullmatch(str(args.get("market_id", ""))):
        errors.append("invalid_market_id")
    if args.get("mode") not in {"trend_trading", "trend_battle"}:
        errors.append("invalid_mode")
    if not str(args.get("question", "")).strip() or len(str(args.get("question", "")).encode()) > 500:
        errors.append("invalid_question")
    choices = args.get("choices")
    if not isinstance(choices, list) or len(choices) != 2:
        errors.append("invalid_choices")
    elif not all(isinstance(c, str) and c.strip() and len(c) <= 64 for c in choices):
        errors.append("invalid_choices")
    elif choices[0] == choices[1]:
        errors.append("invalid_choices")
    if not SLUG_RE.fullmatch(str(args.get("source_id", ""))):
        errors.append("invalid_source_id")
    if not DIGEST_RE.fullmatch(str(args.get("rule_hash", ""))):
        errors.append("invalid_rule_hash")
    try:
        open_at = int(args["open_at"])
        close_at = int(args["close_at"])
        resolve_after = int(args["resolve_after"])
    except (KeyError, TypeError, ValueError):
        errors.append("invalid_timing")
        open_at = close_at = resolve_after = 0
    if not (open_at < close_at <= resolve_after):
        errors.append("invalid_timing")
    if args.get("invalidation_policy") != "refund_on_void":
        errors.append("invalid_invalidation_policy")
    if args.get("mode") == "trend_trading":
        if args.get("battle") is not None:
            errors.append("unexpected_battle")
    elif args.get("mode") == "trend_battle":
        battle = args.get("battle")
        if not isinstance(battle, dict):
            errors.append("missing_battle")
        else:
            topic_objects = []
            for key in ("topic_a", "topic_b"):
                topic = battle.get(key) or {}
                topic_objects.append(topic)
                for field in ("topic_id", "source_id", "project", "article_title", "metric"):
                    if not topic.get(field):
                        errors.append(f"invalid_battle_{key}_{field}")
                if topic.get("source_id") != args.get("source_id"):
                    errors.append(f"battle_{key}_source_mismatch")
            if len(topic_objects) == 2:
                if topic_objects[0].get("topic_id") == topic_objects[1].get("topic_id"):
                    errors.append("battle_topics_not_distinct")
                if topic_objects[0].get("article_title") == topic_objects[1].get("article_title"):
                    errors.append("battle_topics_not_distinct")
                if (
                    topic_objects[0].get("project") != topic_objects[1].get("project")
                    or topic_objects[0].get("metric") != topic_objects[1].get("metric")
                ):
                    errors.append("battle_topics_incompatible")
            if battle.get("formula") != "growth_comparison_v1":
                errors.append("invalid_battle_formula")
            if battle.get("tie_policy") != "void":
                errors.append("invalid_tie_policy")
            try:
                start = int(battle["observation_start"])
                end = int(battle["observation_end"])
            except (KeyError, TypeError, ValueError):
                errors.append("invalid_observation_window")
                start = end = 0
            if not (start < end <= resolve_after):
                errors.append("invalid_observation_window")
            try:
                min_baseline = int(battle["min_baseline_views"])
            except (KeyError, TypeError, ValueError):
                errors.append("invalid_min_baseline")
                min_baseline = 0
            if min_baseline <= 0:
                errors.append("invalid_min_baseline")
            tolerance = battle.get("tie_tolerance_bps")
            if not isinstance(tolerance, int) or not 0 <= tolerance <= 10000:
                errors.append("invalid_tie_tolerance")
    return errors
