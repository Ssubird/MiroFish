"""Hybrid lottery agents that combine stats and metaphysics context."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..models import PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .helpers import draw_terms, energy_similarity, hot_counts, miss_streaks, rank_scores, recent_history, select_numbers


GROUP = "hybrid"


def _graph_alignment(context: PredictionContext, number: int, history_scores: Counter) -> float:
    graph_score = float(context.graph_snapshot.concept_scores.get(str(number), 0.0))
    return graph_score + history_scores[number] * 0.1


@dataclass(frozen=True)
class HybridResonanceAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        counts = hot_counts(segment)
        streaks = miss_streaks(segment)
        scores = {number: 0.0 for number in range(1, 81)}
        for draw in segment:
            similarity = energy_similarity(draw, context.target_draw)
            graph_score = sum(context.graph_snapshot.concept_scores.get(term, 0.0) for term in draw_terms(draw))
            for number in draw.numbers:
                scores[number] += similarity * 0.8 + graph_score * 0.06
        for number in range(1, 81):
            scores[number] += counts[number] * 1.6 + streaks[number] * 0.35
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="用统计频次、遗漏、图谱概念权重和能量相似度一起打分。",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class HybridBridgeAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        counts = hot_counts(segment)
        history_scores = Counter(number for draw in context.history_draws[-36:] for number in draw.numbers)
        graph_terms = set(context.graph_snapshot.highlights[:8])
        scores = {}
        for number in range(1, 81):
            value = counts[number] * 1.4 + _graph_alignment(context, number, history_scores)
            if graph_terms:
                value += sum(1.2 for term in graph_terms if str(number).endswith(term[-1:]))
            scores[number] = value
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="把近窗热点、图谱高频概念和近期号码桥接到同一评分面板。",
            ranked_scores=rank_scores(scores, pick_size),
        )


def build_hybrid_agents() -> dict[str, StrategyAgent]:
    agents = [
        HybridResonanceAgent("hybrid_resonance_160", "混合共振-160期", "融合数据频次、能量和图谱概念。", 160, GROUP, window=160),
        HybridBridgeAgent("hybrid_bridge_100", "混合桥接-100期", "把图谱概念和近窗热点压到同一个候选池。", 100, GROUP, window=100),
    ]
    return {agent.strategy_id: agent for agent in agents}
