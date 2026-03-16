"""Small helpers for runtime assembly."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .constants import RANKED_SCORE_PREVIEW
from .serializers import serialize_prediction


FALLBACK_CONFIDENCE_FLOOR = 1.0


def grouped_strategies(strategies: dict[str, object], groups: tuple[str, ...]) -> dict[str, object]:
    return {key: value for key, value in strategies.items() if value.group in groups}


def by_group(strategies: dict[str, object], group: str) -> dict[str, object]:
    return {key: value for key, value in strategies.items() if value.group == group}


def serialized_predictions(
    predictions: dict[str, object],
    leaderboard: list[dict[str, object]],
) -> list[dict[str, object]]:
    metrics_by_id = {
        item["strategy_id"]: {
            "average_hits": float(item["average_hits"]),
            "objective_score": float(item.get("objective_score", 0.0)),
            "strategy_roi": float(item.get("strategy_roi", 0.0)),
        }
        for item in leaderboard
    }
    return [
        serialize_prediction(prediction, metrics_by_id.get(strategy_id, {}), RANKED_SCORE_PREVIEW)
        for strategy_id, prediction in predictions.items()
    ]


def contributor_breakdown(
    predictions: dict[str, object],
    contributors: list[dict[str, object]],
) -> dict[int, dict[str, object]]:
    breakdown = defaultdict(lambda: {"score": 0.0, "sources": []})
    for contributor in contributors:
        prediction = predictions[contributor["strategy_id"]]
        weight = float(contributor.get("objective_score", 0.0)) / max(contributor["group_rank"], 1)
        for number, confidence in _number_confidences(prediction).items():
            breakdown[number]["score"] += weight * confidence
            if prediction.display_name not in breakdown[number]["sources"]:
                breakdown[number]["sources"].append(prediction.display_name)
    return breakdown


def _number_confidences(prediction: object) -> dict[int, float]:
    numbers = [int(value) for value in getattr(prediction, "numbers", ())]
    fallback = _normalized(_fallback_weights(numbers))
    ranked = _ranked_weights(numbers, getattr(prediction, "ranked_scores", ()))
    if not ranked:
        return fallback
    merged = {number: ranked.get(number, fallback[number]) for number in numbers}
    return _normalized(merged)


def _ranked_weights(numbers: list[int], ranked_scores: Iterable[tuple[int, float]]) -> dict[int, float]:
    weights = {}
    number_set = set(numbers)
    for number, score in ranked_scores:
        value = max(float(score), 0.0)
        if int(number) in number_set and value > 0.0:
            weights[int(number)] = value
    return weights


def _fallback_weights(numbers: list[int]) -> dict[int, float]:
    total = len(numbers)
    return {
        number: float(max(total - index, FALLBACK_CONFIDENCE_FLOOR))
        for index, number in enumerate(numbers)
    }


def _normalized(weights: dict[int, float]) -> dict[int, float]:
    total = sum(max(value, 0.0) for value in weights.values())
    if total <= 0.0:
        return {number: 0.0 for number in weights}
    return {number: max(value, 0.0) / total for number, value in weights.items()}
