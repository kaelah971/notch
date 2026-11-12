"""Deterministic integer arithmetic for S3B outcomes."""

from __future__ import annotations

from typing import Iterable

MAX_VIEWS = 2**64 - 1
MAX_BPS = 10**24


class CalculationError(ValueError):
    pass


def validate_views(label: str, views: int) -> int:
    if not isinstance(views, int) or isinstance(views, bool):
        raise CalculationError(f"{label} must be an integer")
    if views < 0 or views > MAX_VIEWS:
        raise CalculationError(f"{label} outside u64 range: {views}")
    return views


def growth_bps(baseline_views: int, target_views: int) -> int:
    """floor((target - baseline) * 10000 / baseline), mathematical floor."""
    validate_views("baseline_views", baseline_views)
    validate_views("target_views", target_views)
    if baseline_views <= 0:
        raise CalculationError("baseline_views must be greater than zero")
    result = ((target_views - baseline_views) * 10000) // baseline_views
    if abs(result) > MAX_BPS:
        raise CalculationError("growth_bps outside deterministic bound")
    return result


def trend_outcome(growth: int, threshold_bps: int) -> str:
    if not isinstance(threshold_bps, int) or threshold_bps < 0:
        raise CalculationError("threshold_bps must be a non-negative integer")
    return "UP" if growth >= threshold_bps else "DOWN"


def battle_outcome(growth_a: int, growth_b: int, tie_tolerance_bps: int) -> str:
    if not isinstance(tie_tolerance_bps, int) or tie_tolerance_bps < 0:
        raise CalculationError("tie_tolerance_bps must be a non-negative integer")
    difference = growth_a - growth_b
    if abs(difference) <= tie_tolerance_bps:
        return "TIE"
    return "TOPIC_A" if difference > 0 else "TOPIC_B"


def battle_difference(growth_a: int, growth_b: int) -> int:
    return growth_a - growth_b


def percentile(values: Iterable[int], p: int) -> int | None:
    """Nearest-rank percentile (ceil(p*n/100)-1). Deterministic."""
    if not 0 <= p <= 100:
        raise CalculationError("percentile must be 0..100")
    ordered = sorted(values)
    if not ordered:
        return None
    index = (p * len(ordered) + 99) // 100 - 1
    index = max(0, min(index, len(ordered) - 1))
    return ordered[index]


def round_up(value: int, step: int) -> int:
    if step <= 0:
        raise CalculationError("step must be positive")
    if value <= 0:
        return 0
    return ((value + step - 1) // step) * step


def growth_stats(values: Iterable[int]) -> dict[str, int | None]:
    ordered = sorted(values)
    if not ordered:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "max": None,
            "mean_abs": None,
        }
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p10": percentile(ordered, 10),
        "p25": percentile(ordered, 25),
        "p50": percentile(ordered, 50),
        "p75": percentile(ordered, 75),
        "p90": percentile(ordered, 90),
        "max": ordered[-1],
        "mean_abs": sum(abs(value) for value in ordered) // len(ordered),
    }


def trend_calculation(
    baseline_views: int,
    target_views: int,
    threshold_bps: int,
    min_baseline_views: int,
) -> dict:
    if baseline_views < min_baseline_views:
        return {
            "outcome": "INVALID",
            "invalidity_reason": "baseline_below_minimum",
            "baseline_views": baseline_views,
            "target_views": target_views,
            "growth_bps": None,
            "threshold_bps": threshold_bps,
        }
    growth = growth_bps(baseline_views, target_views)
    return {
        "outcome": trend_outcome(growth, threshold_bps),
        "invalidity_reason": None,
        "baseline_views": baseline_views,
        "target_views": target_views,
        "growth_bps": growth,
        "threshold_bps": threshold_bps,
    }


def battle_calculation(
    baseline_a: int,
    target_a: int,
    baseline_b: int,
    target_b: int,
    tie_tolerance_bps: int,
    min_baseline_views: int,
) -> dict:
    if baseline_a < min_baseline_views or baseline_b < min_baseline_views:
        return {
            "outcome": "INVALID",
            "invalidity_reason": "baseline_below_minimum",
            "baseline_a": baseline_a,
            "target_a": target_a,
            "baseline_b": baseline_b,
            "target_b": target_b,
            "growth_a_bps": None,
            "growth_b_bps": None,
            "difference_bps": None,
            "tie_tolerance_bps": tie_tolerance_bps,
        }
    growth_a = growth_bps(baseline_a, target_a)
    growth_b = growth_bps(baseline_b, target_b)
    difference = battle_difference(growth_a, growth_b)
    return {
        "outcome": battle_outcome(growth_a, growth_b, tie_tolerance_bps),
        "invalidity_reason": None,
        "baseline_a": baseline_a,
        "target_a": target_a,
        "baseline_b": baseline_b,
        "target_b": target_b,
        "growth_a_bps": growth_a,
        "growth_b_bps": growth_b,
        "difference_bps": difference,
        "tie_tolerance_bps": tie_tolerance_bps,
    }
