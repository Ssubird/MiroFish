"""Data-driven lottery strategy agents."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..models import StrategyPrediction
from .base import StrategyAgent
from .helpers import hot_counts, miss_streaks, rank_scores, recent_history, region_index, select_numbers, tail_index


GROUP = "data"
SHORT_WINDOW = 12


@dataclass(frozen=True)
class HotWindowAgent(StrategyAgent):
    window: int

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        counts = hot_counts(segment)
        streaks = miss_streaks(segment)
        scores = {number: counts[number] * 10.0 + streaks[number] * 0.1 for number in range(1, 81)}
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"统计最近 {self.window} 期热号频次，并用遗漏长度做轻微打散。",
            ranked_scores=rank_scores(scores, pick_size),
        )


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
            rationale=f"优先选择最近 {self.window} 期内出现偏少且遗漏拉长的号码。",
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
            rationale=f"按最近 {self.window} 期的遗漏长度排序，偏向长缺口号码。",
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
            rationale=f"比较最近 {SHORT_WINDOW} 期与 {self.window} 期的频次差，捕捉升温号码。",
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
            rationale="优先补足近期弱势分区和尾数组合，避免号码过度集中。",
            ranked_scores=rank_scores(scores, pick_size),
        )


def build_data_agents() -> dict[str, StrategyAgent]:
    agents = [
        HotWindowAgent("hot_50", "热号-50期", "统计最近 50 期高频号码。", 50, GROUP, window=50),
        ColdWindowAgent("cold_50", "冷号-50期", "结合冷号与遗漏长度排序。", 50, GROUP, window=50),
        MissStreakAgent("miss_120", "遗漏-120期", "按最近 120 期遗漏长度排序。", 120, GROUP, window=120),
        MomentumShiftAgent("momentum_60", "动量-60期", "比较短窗和长窗频次差，抓升温号码。", 60, GROUP, window=60),
        StructureBalanceAgent("structure_90", "结构均衡-90期", "按分区和尾数的弱势结构补位。", 90, GROUP, window=90),
    ]
    return {agent.strategy_id: agent for agent in agents}
