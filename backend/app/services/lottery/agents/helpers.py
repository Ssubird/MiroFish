"""Shared helpers for grouped lottery agents."""

from __future__ import annotations

from collections import Counter

from ..models import DrawRecord


NUMBER_START = 1
NUMBER_END = 80
NUMBER_SCORE_PREVIEW = 15
RECENCY_WEIGHT = 0.35
MUTAGEN_DAILY_WEIGHT = 3.0
MUTAGEN_HOURLY_WEIGHT = 2.0
STEM_MATCH_WEIGHT = 1.6
BRANCH_MATCH_WEIGHT = 1.6
REGION_SIZE = 20


def all_numbers() -> range:
    return range(NUMBER_START, NUMBER_END + 1)


def recent_history(history: tuple[DrawRecord, ...], window: int) -> tuple[DrawRecord, ...]:
    if len(history) < window:
        raise ValueError(f"策略需要至少 {window} 期历史数据，当前只有 {len(history)} 期")
    return history[-window:]


def miss_streaks(history: tuple[DrawRecord, ...]) -> dict[int, int]:
    total = len(history)
    streaks = {number: total for number in all_numbers()}
    for reverse_index, draw in enumerate(reversed(history), start=1):
        for number in draw.numbers:
            if streaks[number] == total:
                streaks[number] = reverse_index - 1
    return streaks


def rank_scores(scores: dict[int, float], pick_size: int) -> tuple[tuple[int, float], ...]:
    limit = max(pick_size, NUMBER_SCORE_PREVIEW)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return tuple(ordered[:limit])


def select_numbers(scores: dict[int, float], pick_size: int) -> tuple[int, ...]:
    return tuple(number for number, _ in rank_scores(scores, pick_size)[:pick_size])


def energy_similarity(source: DrawRecord, target: DrawRecord) -> float:
    daily_overlap = len(set(source.daily_energy.mutagen) & set(target.daily_energy.mutagen))
    hourly_overlap = len(set(source.hourly_energy.mutagen) & set(target.hourly_energy.mutagen))
    similarity = daily_overlap * MUTAGEN_DAILY_WEIGHT
    similarity += hourly_overlap * MUTAGEN_HOURLY_WEIGHT
    similarity += STEM_MATCH_WEIGHT * (source.daily_energy.stem == target.daily_energy.stem)
    similarity += STEM_MATCH_WEIGHT * (source.hourly_energy.stem == target.hourly_energy.stem)
    similarity += BRANCH_MATCH_WEIGHT * (source.daily_energy.branch == target.daily_energy.branch)
    similarity += BRANCH_MATCH_WEIGHT * (source.hourly_energy.branch == target.hourly_energy.branch)
    return similarity


def recency_factor(index: int, total: int) -> float:
    return 1.0 + RECENCY_WEIGHT * (index / max(total, 1))


def region_index(number: int) -> int:
    return min((number - 1) // REGION_SIZE, 3)


def tail_index(number: int) -> int:
    return number % 10


def hot_counts(history: tuple[DrawRecord, ...]) -> Counter:
    return Counter(number for draw in history for number in draw.numbers)


def draw_terms(draw: DrawRecord) -> tuple[str, ...]:
    return (
        *draw.daily_energy.mutagen,
        *draw.hourly_energy.mutagen,
        draw.daily_energy.stem,
        draw.daily_energy.branch,
        draw.hourly_energy.stem,
        draw.hourly_energy.branch,
    )
