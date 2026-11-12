"""Historical volatility and threshold calibration from Wikimedia pageviews."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from services.trend_radar.canonical import canonical_json, sha256_text
from services.trend_radar.models import iso_utc, jsonable

from .calculations import growth_bps, growth_stats, percentile, round_up
from .models import CALIBRATION_SCHEMA, CalibrationReport, PageviewsRange
from .wikimedia import PROJECT

CALIBRATION_DAYS = 56
MIN_CALIBRATION_SAMPLES = 20
MIN_BASELINE_VIEWS = 1000
THRESHOLD_STEP_BPS = 50
THRESHOLD_MAX_BPS = 10000
TIE_STEP_BPS = 10
TIE_MAX_BPS = 1000
TIE_PERCENTILE = 10
THRESHOLD_POLICY = (
    "threshold-calibration-v1: nearest-rank p75 of historical 7-day growth, "
    "clamped to [0, 10000] and rounded up to 50 bps"
)
TIE_POLICY_TEXT = (
    "tie-calibration-v1: nearest-rank p10 of historical absolute 7-day growth "
    "differences, clamped to [0, 500] and rounded up to 10 bps"
)


class CalibrationError(ValueError):
    pass


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _weekly_growth(
    pageviews: PageviewsRange, start: date, end: date
) -> dict[str, int]:
    result: dict[str, int] = {}
    day = start
    while day <= end:
        previous = day - timedelta(days=7)
        current = pageviews.observations.get(day.isoformat())
        prior = pageviews.observations.get(previous.isoformat())
        if current and prior and prior.views > 0:
            result[day.isoformat()] = growth_bps(prior.views, current.views)
        day += timedelta(days=1)
    return result


def _daily_growth(
    pageviews: PageviewsRange, start: date, end: date
) -> dict[str, int]:
    result: dict[str, int] = {}
    day = start
    while day <= end:
        previous = day - timedelta(days=1)
        current = pageviews.observations.get(day.isoformat())
        prior = pageviews.observations.get(previous.isoformat())
        if current and prior and prior.views > 0:
            result[day.isoformat()] = growth_bps(prior.views, current.views)
        day += timedelta(days=1)
    return result


def _window_has_complete_history(
    pageviews: PageviewsRange, start: date, end: date
) -> tuple[bool, list[str]]:
    missing = []
    day = start
    while day <= end:
        if day.isoformat() not in pageviews.observations:
            missing.append(day.isoformat())
        day += timedelta(days=1)
    return not missing, missing


def _base_report(
    *,
    mode: str,
    article: str | None,
    baseline_date: date,
    target_date: date,
    calibration_end: date,
    min_baseline_views: int,
    ranges: list[PageviewsRange],
) -> CalibrationReport:
    calibration_start = calibration_end - timedelta(days=CALIBRATION_DAYS - 1)
    missing = sorted(
        {
            missing_date
            for pageviews in ranges
            for missing_date in pageviews.missing_dates
        }
    )
    source_queries = sorted({pageviews.source_url for pageviews in ranges})
    source_hashes = sorted(
        {
            pageviews.raw_response_hash
            for pageviews in ranges
            if pageviews.raw_response_hash
        }
    )
    retrieved = [pageviews.retrieved_at for pageviews in ranges if pageviews.retrieved_at]
    return CalibrationReport(
        schema_version=CALIBRATION_SCHEMA,
        mode=mode,
        article=article,
        project=PROJECT,
        baseline_date=baseline_date.isoformat(),
        target_date=target_date.isoformat(),
        calibration_start=calibration_start.isoformat(),
        calibration_end=calibration_end.isoformat(),
        calibration_days=CALIBRATION_DAYS,
        min_baseline_views=min_baseline_views,
        observation_status="PENDING",
        baseline_views=None,
        target_views=None,
        weekly_growth_bps={},
        weekly_growth_stats={},
        daily_growth_stats={},
        suggested_threshold_bps=None,
        threshold_candidates={},
        threshold_policy=THRESHOLD_POLICY,
        up_frequency_at_threshold=None,
        status="HOLD",
        reasons=[],
        missing_dates=missing,
        source_queries=source_queries,
        source_raw_hashes=source_hashes,
        retrieved_at=max(retrieved) if retrieved else None,
    )


def _finalize_report(report: CalibrationReport) -> CalibrationReport:
    report_dict = jsonable(report)
    report_dict.pop("report_digest", None)
    # Retrieval wall-clock metadata is preserved for audit but is not part of
    # the reproducible evidence content.
    report_dict.pop("retrieved_at", None)
    digest = "sha256:" + sha256_text(canonical_json(report_dict))
    report.report_digest = digest
    return report


def _calibration_guards(
    report: CalibrationReport,
    *,
    ranges: list[PageviewsRange],
    baseline_date: date,
    target_date: date,
    calibration_end: date,
    replay: bool,
) -> None:
    if not replay and target_date > calibration_end:
        # Future market: target observations are expected to be absent.
        report.observation_status = "PENDING_OBSERVATION"
    if calibration_end >= baseline_date:
        report.status = "HOLD"
        report.reasons.append("lookahead_calibration_window")
    if any(pageviews.error for pageviews in ranges):
        report.status = "HOLD"
        report.reasons.append("source_retrieval_error")
        for pageviews in ranges:
            if pageviews.error:
                report.missing_dates.extend(
                    day
                    for day in [pageviews.start_date]
                    if day not in report.missing_dates
                )
    if any(pageviews.duplicate_dates for pageviews in ranges):
        report.status = "HOLD"
        report.reasons.append("duplicate_source_observations")
    if report.missing_dates:
        report.status = "HOLD"
        report.reasons.append("missing_source_observations")
    if report.weekly_growth_stats.get("count", 0) < MIN_CALIBRATION_SAMPLES:
        report.status = "HOLD"
        report.reasons.append("insufficient_calibration_samples")
    if report.observation_status == "PENDING":
        if replay:
            report.status = "HOLD"
            report.reasons.append("missing_baseline_or_target_observation")
        else:
            report.observation_status = "PENDING_OBSERVATION"


def calibrate_trend(
    pageviews: PageviewsRange,
    *,
    baseline_date: date,
    target_date: date,
    calibration_end: date,
    replay: bool,
    min_baseline_views: int = MIN_BASELINE_VIEWS,
) -> CalibrationReport:
    if target_date <= baseline_date:
        raise CalibrationError("target_date must be after baseline_date")
    report = _base_report(
        mode="trend_trading",
        article=pageviews.article,
        baseline_date=baseline_date,
        target_date=target_date,
        calibration_end=calibration_end,
        min_baseline_views=min_baseline_views,
        ranges=[pageviews],
    )
    start = date.fromisoformat(report.calibration_start)
    weekly = _weekly_growth(pageviews, start, calibration_end)
    daily = _daily_growth(pageviews, start, calibration_end)
    report.weekly_growth_bps = weekly
    report.weekly_growth_stats = growth_stats(weekly.values())
    report.daily_growth_stats = growth_stats(daily.values())

    threshold_candidates = {
        "p50": percentile(weekly.values(), 50),
        "p75": percentile(weekly.values(), 75),
        "p90": percentile(weekly.values(), 90),
    }
    report.threshold_candidates = threshold_candidates
    p75 = threshold_candidates["p75"]
    if p75 is not None:
        suggestion = min(
            THRESHOLD_MAX_BPS, round_up(max(0, p75), THRESHOLD_STEP_BPS)
        )
        report.suggested_threshold_bps = suggestion
        if weekly:
            report.up_frequency_at_threshold = sum(
                1 for value in weekly.values() if value >= suggestion
            ) * 10000 // len(weekly)

    baseline = pageviews.observations.get(baseline_date.isoformat())
    target = pageviews.observations.get(target_date.isoformat())
    report.baseline_views = baseline.views if baseline else None
    report.target_views = target.views if target else None
    if baseline and target:
        report.observation_status = "AVAILABLE"
    elif not replay:
        report.observation_status = "PENDING_OBSERVATION"
    if replay and (baseline is None or target is None):
        report.reasons.append("missing_baseline_or_target_observation")
    if baseline is not None and baseline.views < min_baseline_views:
        report.status = "HOLD"
        report.reasons.append("baseline_below_minimum")
    if replay and baseline is not None and target is not None:
        report.status = "OK" if not report.reasons else "HOLD"
    elif not replay:
        report.status = "OK" if not report.reasons else "HOLD"
    else:
        report.status = "HOLD"

    _calibration_guards(
        report,
        ranges=[pageviews],
        baseline_date=baseline_date,
        target_date=target_date,
        calibration_end=calibration_end,
        replay=replay,
    )
    if report.reasons:
        report.status = "HOLD"
    return _finalize_report(report)


def calibrate_battle(
    pageviews_a: PageviewsRange,
    pageviews_b: PageviewsRange,
    *,
    baseline_date: date,
    target_date: date,
    calibration_end: date,
    replay: bool,
    min_baseline_views: int = MIN_BASELINE_VIEWS,
) -> CalibrationReport:
    if target_date <= baseline_date:
        raise CalibrationError("target_date must be after baseline_date")
    report = _base_report(
        mode="trend_battle",
        article=pageviews_a.article,
        baseline_date=baseline_date,
        target_date=target_date,
        calibration_end=calibration_end,
        min_baseline_views=min_baseline_views,
        ranges=[pageviews_a, pageviews_b],
    )
    report.topic_b_article = pageviews_b.article
    report.tie_policy = "void"
    start = date.fromisoformat(report.calibration_start)
    growth_a = _weekly_growth(pageviews_a, start, calibration_end)
    growth_b = _weekly_growth(pageviews_b, start, calibration_end)
    shared_days = sorted(set(growth_a) & set(growth_b))
    differences = [growth_a[day] - growth_b[day] for day in shared_days]
    abs_differences = [abs(value) for value in differences]
    report.abs_difference_stats = growth_stats(abs_differences)
    p10 = percentile(abs_differences, TIE_PERCENTILE)
    if p10 is not None:
        suggestion = min(TIE_MAX_BPS, round_up(max(0, p10), TIE_STEP_BPS))
        report.suggested_tie_tolerance_bps = suggestion
        if abs_differences:
            report.tie_frequency_at_suggestion = (
                sum(1 for value in abs_differences if value <= suggestion)
                * 10000
                // len(abs_differences)
            )
    report.weekly_growth_stats = growth_stats(differences)

    baseline_a = pageviews_a.observations.get(baseline_date.isoformat())
    target_a = pageviews_a.observations.get(target_date.isoformat())
    baseline_b = pageviews_b.observations.get(baseline_date.isoformat())
    target_b = pageviews_b.observations.get(target_date.isoformat())
    report.baseline_views = baseline_a.views if baseline_a else None
    report.target_views = target_a.views if target_a else None
    if baseline_a and target_a and baseline_b and target_b:
        report.observation_status = "AVAILABLE"
        report.growth_a_bps = growth_bps(baseline_a.views, target_a.views)
        report.growth_b_bps = growth_bps(baseline_b.views, target_b.views)
        report.difference_bps = report.growth_a_bps - report.growth_b_bps
    elif not replay:
        report.observation_status = "PENDING_OBSERVATION"
    if replay and not (baseline_a and target_a and baseline_b and target_b):
        report.reasons.append("missing_baseline_or_target_observation")
    if (
        baseline_a is not None
        and baseline_b is not None
        and min(baseline_a.views, baseline_b.views) < min_baseline_views
    ):
        report.status = "HOLD"
        report.reasons.append("baseline_below_minimum")
    if report.abs_difference_stats.get("count", 0) < MIN_CALIBRATION_SAMPLES:
        report.status = "HOLD"
        report.reasons.append("insufficient_calibration_samples")
    if not report.reasons:
        report.status = "OK"
    else:
        report.status = "HOLD"
    _calibration_guards(
        report,
        ranges=[pageviews_a, pageviews_b],
        baseline_date=baseline_date,
        target_date=target_date,
        calibration_end=calibration_end,
        replay=replay,
    )
    if report.reasons:
        report.status = "HOLD"
    return _finalize_report(report)
