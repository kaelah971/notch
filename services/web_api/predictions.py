"""Deterministic prediction-result classification from finalized market state."""

from __future__ import annotations

from typing import Any

PREDICTION_STATUSES = frozenset({"PENDING", "CORRECT", "INCORRECT", "VOIDED", "UNKNOWN"})


def classify_prediction(market: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    """Classify one account's market-level position without using live signals.

    A contract position is one prediction record per market. Repeated entries on the
    same side are represented by one aggregate stake. If a position has stakes on
    both sides, a settled result cannot be called correct or incorrect because there
    is no single original call; it is therefore UNKNOWN. Void/tie resolution still
    classifies as VOIDED because the market itself was refunded.
    """
    choices = market.get("choices")
    stakes = position.get("stakes")
    if not isinstance(choices, list) or not choices or not isinstance(stakes, list):
        return {"status": "UNKNOWN", "choice": None, "choices": []}

    selected: list[int] = []
    try:
        for index, stake in enumerate(stakes):
            if int(stake) > 0:
                selected.append(index)
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "choice": None, "choices": []}

    selected_choices = [str(choices[index]) for index in selected if index < len(choices)]
    if not selected_choices or len(selected_choices) != len(selected):
        return {"status": "UNKNOWN", "choice": None, "choices": selected_choices}
    selected_choice = selected_choices[0] if len(selected_choices) == 1 else None

    market_status = market.get("status")
    resolution_kind = market.get("resolution_kind")
    if market_status == "voided" or resolution_kind in {"void", "tie"}:
        status = "VOIDED"
    elif market_status in {"open", "closed"}:
        status = "PENDING"
    elif market_status == "resolved":
        winner = market.get("winning_outcome")
        try:
            valid_winner = isinstance(winner, int) and not isinstance(winner, bool) and 0 <= winner < len(choices)
        except TypeError:
            valid_winner = False
        if len(selected) != 1 or not valid_winner:
            status = "UNKNOWN"
        else:
            status = "CORRECT" if selected[0] == winner else "INCORRECT"
    else:
        status = "UNKNOWN"

    return {
        "status": status,
        "choice": selected_choice,
        "choices": selected_choices,
    }


def accuracy_percent(correct: int, incorrect: int) -> float | None:
    """Return correct/(correct+incorrect)*100, or None with no completed sample."""
    denominator = correct + incorrect
    if denominator == 0:
        return None
    return correct / denominator * 100
