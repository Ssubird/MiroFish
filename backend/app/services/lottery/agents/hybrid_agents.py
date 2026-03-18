"""Hybrid lottery agents that combine stats and metaphysics context."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..models import PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .helpers import draw_terms, energy_similarity, hot_counts, miss_streaks, rank_scores, recent_history, select_numbers


GROUP = "hybrid"
WINDOW = 160
GRAPH_NUMBER_WEIGHT = 0.3
HISTORY_NUMBER_WEIGHT = 0.15
SIMILARITY_WEIGHT = 0.9
GRAPH_TERM_WEIGHT = 0.07
HOT_WEIGHT = 1.4
MISS_WEIGHT = 0.3


def _recent_number_activity(context: PredictionContext) -> Counter:
    return Counter(number for draw in context.history_draws[-36:] for number in draw.numbers)


@dataclass(frozen=True)
class HybridFusedBoardAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        counts = hot_counts(segment)
        streaks = miss_streaks(segment)
        recent_scores = _recent_number_activity(context)
        scores = {number: 0.0 for number in range(1, 81)}

        for draw in segment:
            similarity = energy_similarity(draw, context.target_draw)
            graph_score = sum(context.graph_snapshot.concept_scores.get(term, 0.0) for term in draw_terms(draw))
            for number in draw.numbers:
                scores[number] += similarity * SIMILARITY_WEIGHT + graph_score * GRAPH_TERM_WEIGHT

        for number in range(1, 81):
            scores[number] += counts[number] * HOT_WEIGHT
            scores[number] += streaks[number] * MISS_WEIGHT
            scores[number] += float(context.graph_snapshot.concept_scores.get(str(number), 0.0)) * GRAPH_NUMBER_WEIGHT
            scores[number] += recent_scores[number] * HISTORY_NUMBER_WEIGHT

        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="Blend recent stats, graph terms, number-level graph cues, and energy similarity.",
            ranked_scores=rank_scores(scores, pick_size),
            metadata={"graph_snapshot": context.graph_snapshot.snapshot_id},
        )


def build_hybrid_agents() -> dict[str, StrategyAgent]:
    agent = HybridFusedBoardAgent(
        "hybrid_fused_board",
        "Hybrid Fused Board",
        "Blend data factors with metaphysics factors into one board.",
        WINDOW,
        GROUP,
        window=WINDOW,
    )
    return {agent.strategy_id: agent}
