"""Small helpers for runtime assembly."""

from __future__ import annotations

from collections import defaultdict

from .constants import RANKED_SCORE_PREVIEW
from .serializers import serialize_prediction


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
        for number in prediction.numbers:
            breakdown[number]["score"] += weight
            breakdown[number]["sources"].append(prediction.display_name)
    return breakdown
