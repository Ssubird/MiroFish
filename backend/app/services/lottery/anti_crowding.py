"""Handbook-aligned anti-crowding metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import DrawRecord


RECENT_WINDOW = 50
EDGE_NUMBERS = {1, 2, 3, 4, 5, 76, 77, 78, 79, 80}


@dataclass(frozen=True)
class AntiCrowdingSnapshot:
    crowding_penalties: Mapping[str, float]
    payout_surrogates: Mapping[str, float]
    exclusions: tuple[str, ...]


class AntiCrowdingService:
    """Compute handbook-style crowding and payout proxy metrics."""

    def analyze(self, selection: Iterable[int], history: Iterable[DrawRecord]) -> AntiCrowdingSnapshot:
        numbers = sorted({int(value) for value in selection})
        visible_history = list(history)[-RECENT_WINDOW:]
        penalties = {
            "arithmetic_progression": _arithmetic_progression_risk(numbers),
            "symmetry": _symmetry_risk(numbers),
            "geometric_pattern": _geometric_pattern_risk(numbers),
            "prior_winning_copy": _prior_copy_risk(numbers, visible_history),
            "shifted_winning_copy": _shifted_copy_risk(numbers, visible_history),
            "hot_cold_narrative": _hot_cold_narrative_risk(numbers, visible_history),
            "omission_chasing": _omission_chasing_risk(numbers, visible_history),
        }
        penalties["beautiful_math_pattern"] = round(
            max(penalties["arithmetic_progression"], penalties["symmetry"], penalties["geometric_pattern"]),
            4,
        )
        payout = {
            "ac_proxy": _ac_proxy(numbers),
            "edge_number_ratio": round(sum(number in EDGE_NUMBERS for number in numbers) / max(len(numbers), 1), 4),
            "span_ratio": round((numbers[-1] - numbers[0]) / 79 if len(numbers) > 1 else 0.0, 4),
            "cluster_count": float(_cluster_count(numbers)),
        }
        exclusions = tuple(name for name, value in penalties.items() if value >= 0.75)
        return AntiCrowdingSnapshot(penalties, payout, exclusions)


def _arithmetic_progression_risk(numbers: list[int]) -> float:
    if len(numbers) < 3:
        return 0.0
    diffs = [right - left for left, right in zip(numbers, numbers[1:])]
    if len(set(diffs)) == 1:
        return 1.0
    return round(max(Counter(diffs).values()) / len(diffs), 4)


def _symmetry_risk(numbers: list[int]) -> float:
    if len(numbers) < 2:
        return 0.0
    center = (numbers[0] + numbers[-1]) / 2
    mirrored = sum(1 for number in numbers if (center * 2 - number) in numbers)
    return round(mirrored / len(numbers), 4)


def _geometric_pattern_risk(numbers: list[int]) -> float:
    if len(numbers) < 3 or 0 in numbers[:-1]:
        return 0.0
    ratios = []
    for left, right in zip(numbers, numbers[1:]):
        if left == 0:
            continue
        ratios.append(round(right / left, 2))
    if not ratios:
        return 0.0
    return round(max(Counter(ratios).values()) / len(ratios), 4)


def _prior_copy_risk(numbers: list[int], history: list[DrawRecord]) -> float:
    target = tuple(numbers)
    return 1.0 if any(tuple(sorted(draw.numbers)) == target for draw in history if draw.numbers) else 0.0


def _shifted_copy_risk(numbers: list[int], history: list[DrawRecord]) -> float:
    target = tuple(numbers)
    for draw in history:
        if not draw.numbers or len(draw.numbers) != len(numbers):
            continue
        for delta in (-1, 1):
            shifted = tuple(sorted(number + delta for number in draw.numbers if 1 <= number + delta <= 80))
            if shifted == target:
                return 1.0
    return 0.0


def _hot_cold_narrative_risk(numbers: list[int], history: list[DrawRecord]) -> float:
    counter: Counter[int] = Counter()
    for draw in history:
        counter.update(int(value) for value in draw.numbers)
    if not counter:
        return 0.0
    common = {number for number, _ in counter.most_common(10)}
    rare = {number for number, _ in sorted(counter.items(), key=lambda item: (item[1], item[0]))[:10]}
    touched = sum(number in common or number in rare for number in numbers)
    return round(touched / max(len(numbers), 1), 4)


def _omission_chasing_risk(numbers: list[int], history: list[DrawRecord]) -> float:
    if not history:
        return 0.0
    last_seen = {number: None for number in numbers}
    for offset, draw in enumerate(reversed(history), start=1):
        for number in numbers:
            if last_seen[number] is None and number in draw.numbers:
                last_seen[number] = offset
    long_gap = sum(1 for value in last_seen.values() if value is None or value >= 20)
    return round(long_gap / max(len(numbers), 1), 4)


def _ac_proxy(numbers: list[int]) -> float:
    if len(numbers) < 2:
        return 0.0
    diffs = {right - left for index, left in enumerate(numbers[:-1]) for right in numbers[index + 1 :]}
    baseline = max(len(numbers) - 1, 1)
    return round(max(len(diffs) - baseline, 0) / max(len(numbers) * 2, 1), 4)


def _cluster_count(numbers: list[int]) -> int:
    if not numbers:
        return 0
    clusters = 1
    for left, right in zip(numbers, numbers[1:]):
        if right - left > 2:
            clusters += 1
    return clusters
