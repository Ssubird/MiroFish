"""Data-driven lottery strategy agents."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..models import StrategyPrediction
from .base import StrategyAgent
from .helpers import (
    hot_counts,
    miss_streaks,
    rank_scores,
    recent_history,
    region_index,
    select_numbers,
    tail_index,
)


GROUP = "data"
SHORT_WINDOW = 12
RECENT_BOARD_WINDOW = 50
FREQUENCY_WEIGHT = 10.0
RECENCY_WEIGHT = 0.2


def _recent_board_scores(segment) -> dict[int, float]:
    counts = Counter(number for draw in segment for number in draw.numbers)
    last_seen = {number: -1 for number in range(1, 81)}
    for index, draw in enumerate(segment, start=1):
        for number in draw.numbers:
            last_seen[number] = index
    return {
        number: counts[number] * FREQUENCY_WEIGHT + last_seen[number] * RECENCY_WEIGHT
        for number in range(1, 81)
    }


@dataclass(frozen=True)
class ColdWindowAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        counts = hot_counts(segment)
        streaks = miss_streaks(segment)
        max_count = max(counts.values(), default=0)
        scores = {
            number: (max_count - counts[number]) * 8.0 + streaks[number] * 0.8
            for number in range(1, 81)
        }
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"Rank by coldness and miss streak over the last {self.window} draws.",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class MissStreakAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        streaks = miss_streaks(segment)
        scores = {number: float(streaks[number]) for number in range(1, 81)}
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"Rank by raw miss streak over the last {self.window} draws.",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class MomentumShiftAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        short_segment = segment[-SHORT_WINDOW:]
        long_counts = hot_counts(segment)
        short_counts = hot_counts(short_segment)
        streaks = miss_streaks(segment)
        scores = {}
        for number in range(1, 81):
            momentum = short_counts[number] * 12.0 - long_counts[number] * 2.0
            scores[number] = momentum + streaks[number] * 0.4
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"Compare the last {SHORT_WINDOW} draws against the last {self.window} draws.",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class StructureBalanceAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        region_counts = Counter(region_index(number) for draw in segment for number in draw.numbers)
        tail_counts = Counter(tail_index(number) for draw in segment for number in draw.numbers)
        streaks = miss_streaks(segment)
        max_region = max(region_counts.values(), default=1)
        max_tail = max(tail_counts.values(), default=1)
        scores = {}
        for number in range(1, 81):
            region_score = (max_region - region_counts[region_index(number)]) * 2.4
            tail_score = (max_tail - tail_counts[tail_index(number)]) * 0.8
            scores[number] = region_score + tail_score + streaks[number] * 0.3
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="Balance weak regions and tail groups to avoid over-crowding.",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class RecentBoardAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        scores = _recent_board_scores(segment)
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="Recent 50-issue board ranked by frequency with recency tie-breaks.",
            ranked_scores=rank_scores(scores, pick_size),
            metadata={"window": self.window},
        )


def build_data_agents() -> dict[str, StrategyAgent]:
    agents = [
        ColdWindowAgent("cold_50", "Cold Board 50", "Cold and miss streak board.", 50, GROUP, window=50),
        MissStreakAgent("miss_120", "Miss Board 120", "Longest miss streak board.", 120, GROUP, window=120),
        MomentumShiftAgent("momentum_60", "Momentum Board 60", "Short-vs-long momentum board.", 60, GROUP, window=60),
        StructureBalanceAgent("structure_90", "Structure Board 90", "Region and tail balance board.", 90, GROUP, window=90),
        RecentBoardAgent("recent_board_50", "Recent Board 50", "Recent 50 issue number board.", RECENT_BOARD_WINDOW, GROUP, window=RECENT_BOARD_WINDOW),
    ]
    return {agent.strategy_id: agent for agent in agents}
