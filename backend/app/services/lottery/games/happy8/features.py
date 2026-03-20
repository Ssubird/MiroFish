"""Happy 8 feature extraction for market scoring."""

from __future__ import annotations

from typing import Mapping

from ..base import MarketFeatureProfile


EDGE_NUMBERS = {1, 2, 3, 4, 5, 76, 77, 78, 79, 80}


def default_feature_profile(weights: Mapping[str, float] | None = None) -> MarketFeatureProfile:
    return MarketFeatureProfile(
        game_id="happy8",
        play_mode="default",
        feature_extractors=("sum", "span", "odd_even_balance", "edge_count", "cluster_count", "ac_proxy"),
        crowding_rules=(
            "arithmetic_progression",
            "symmetry",
            "geometric_pattern",
            "prior_winning_copy",
            "shifted_winning_copy",
            "hot_cold_narrative",
            "omission_chasing",
        ),
        payout_surrogate_weights=dict(weights or {"ac_proxy": 1.0, "span_ratio": 0.8, "edge_ratio": -0.4, "cluster_count": 0.6}),
    )


def extract_happy8_features(selection: list[int], play_mode: str) -> dict[str, float]:
    del play_mode
    numbers = sorted({int(value) for value in selection})
    if not numbers:
        return {
            "sum": 0.0,
            "span_ratio": 0.0,
            "odd_even_balance": 0.0,
            "edge_ratio": 0.0,
            "cluster_count": 0.0,
            "ac_proxy": 0.0,
        }
    return {
        "sum": float(sum(numbers)),
        "span_ratio": round((numbers[-1] - numbers[0]) / 79 if len(numbers) > 1 else 0.0, 4),
        "odd_even_balance": round(abs(_odd_count(numbers) - _even_count(numbers)) / len(numbers), 4),
        "edge_ratio": round(sum(number in EDGE_NUMBERS for number in numbers) / len(numbers), 4),
        "cluster_count": float(_cluster_count(numbers)),
        "ac_proxy": _ac_proxy(numbers),
    }


def _odd_count(numbers: list[int]) -> int:
    return sum(number % 2 for number in numbers)


def _even_count(numbers: list[int]) -> int:
    return len(numbers) - _odd_count(numbers)


def _cluster_count(numbers: list[int]) -> int:
    clusters = 1
    for left, right in zip(numbers, numbers[1:]):
        if right - left > 2:
            clusters += 1
    return clusters


def _ac_proxy(numbers: list[int]) -> float:
    if len(numbers) < 2:
        return 0.0
    diffs = {right - left for index, left in enumerate(numbers[:-1]) for right in numbers[index + 1 :]}
    baseline = max(len(numbers) - 1, 1)
    return round(max(len(diffs) - baseline, 0) / max(len(numbers) * 2, 1), 4)
