"""Unified multi-objective scoring for lottery strategy evaluation."""

from __future__ import annotations

from collections import Counter
from statistics import fmean, pstdev

from .happy8_rules import ticket_payout as happy8_ticket_payout


ROI_TICKET_COST_YUAN = 2
ROI_FLOOR = -1.0
ROI_CAP = 3.0
NEUTRAL_ROI_SCORE = 0.5
HIT_RATE_WEIGHT = 0.58
ROI_WEIGHT = 0.27
STABILITY_WEIGHT = 0.10
HEAT_WEIGHT = 0.05


def objective_policy() -> dict[str, object]:
    return {
        "sort_key": "objective_score",
        "weights": {
            "hit_rate": HIT_RATE_WEIGHT,
            "roi": ROI_WEIGHT,
            "stability_penalty": STABILITY_WEIGHT,
            "heat_penalty": HEAT_WEIGHT,
        },
        "roi_bounds": {"floor": ROI_FLOOR, "cap": ROI_CAP},
    }


def objective_metrics(
    issues: list[dict[str, object]],
    pick_size: int | None = None,
) -> dict[str, object]:
    normalized_pick_size = pick_size or _pick_size(issues)
    hits = [int(item.get("hits", 0)) for item in issues]
    average_hits = fmean(hits) if hits else 0.0
    hit_stddev = pstdev(hits) if len(hits) > 1 else 0.0
    average_hit_rate = average_hits / normalized_pick_size if normalized_pick_size else 0.0
    roi_metrics = _roi_metrics(issues, normalized_pick_size)
    heat_penalty = _heat_penalty(issues, normalized_pick_size)
    stability_penalty = _stability_penalty(hit_stddev, normalized_pick_size)
    objective_score = _objective_score(average_hit_rate, roi_metrics["roi_score"], stability_penalty, heat_penalty)
    return {
        "issues_scored": len(hits),
        "total_hits": sum(hits),
        "average_hits": round(average_hits, 4),
        "average_hit_rate": round(average_hit_rate, 4),
        "hit_stddev": round(hit_stddev, 4),
        "max_hits": max(hits) if hits else 0,
        "min_hits": min(hits) if hits else 0,
        "strategy_roi": round(float(roi_metrics["strategy_roi"]), 4),
        "roi_score": round(float(roi_metrics["roi_score"]), 4),
        "roi_supported": bool(roi_metrics["roi_supported"]),
        "heat_penalty": round(heat_penalty, 4),
        "stability_penalty": round(stability_penalty, 4),
        "objective_score": round(objective_score, 4),
        "objective_components": {
            "hit_rate": round(average_hit_rate * HIT_RATE_WEIGHT, 4),
            "roi": round(float(roi_metrics["roi_score"]) * ROI_WEIGHT, 4),
            "stability_penalty": round(stability_penalty * STABILITY_WEIGHT, 4),
            "heat_penalty": round(heat_penalty * HEAT_WEIGHT, 4),
        },
    }


def objective_sort_key(item: dict[str, object]) -> tuple[float, float, float, str]:
    return (
        -float(item.get("objective_score", 0.0)),
        -float(item.get("average_hits", 0.0)),
        float(item.get("hit_stddev", 0.0)),
        str(item.get("strategy_id", "")),
    )


def ticket_payout(pick_size: int, hits: int) -> int:
    return happy8_ticket_payout(pick_size, hits)


def _pick_size(issues: list[dict[str, object]]) -> int:
    if not issues:
        return 0
    predicted = issues[0].get("predicted_numbers") or []
    return len(predicted) if isinstance(predicted, list) else 0


def _roi_metrics(issues: list[dict[str, object]], pick_size: int) -> dict[str, object]:
    if not issues or pick_size < 1:
        return {"strategy_roi": 0.0, "roi_score": NEUTRAL_ROI_SCORE, "roi_supported": False}
    total_cost = len(issues) * ROI_TICKET_COST_YUAN
    total_payout = sum(ticket_payout(pick_size, int(item.get("hits", 0))) for item in issues)
    strategy_roi = (total_payout - total_cost) / total_cost if total_cost else 0.0
    return {
        "strategy_roi": strategy_roi,
        "roi_score": _normalize_roi(strategy_roi),
        "roi_supported": True,
    }


def _normalize_roi(strategy_roi: float) -> float:
    clipped = min(max(strategy_roi, ROI_FLOOR), ROI_CAP)
    return (clipped - ROI_FLOOR) / (ROI_CAP - ROI_FLOOR)


def _heat_penalty(issues: list[dict[str, object]], pick_size: int) -> float:
    if not issues or not pick_size:
        return 0.0
    counter = Counter(number for item in issues for number in item.get("predicted_numbers", []))
    repeated = sum(max(count - 1, 0) for count in counter.values())
    total_predictions = len(issues) * pick_size
    return repeated / total_predictions if total_predictions else 0.0


def _stability_penalty(hit_stddev: float, pick_size: int) -> float:
    if not pick_size:
        return 0.0
    return min(hit_stddev / pick_size, 1.0)


def _objective_score(
    average_hit_rate: float,
    roi_score: float,
    stability_penalty: float,
    heat_penalty: float,
) -> float:
    return (
        average_hit_rate * HIT_RATE_WEIGHT
        + roi_score * ROI_WEIGHT
        - stability_penalty * STABILITY_WEIGHT
        - heat_penalty * HEAT_WEIGHT
    )
