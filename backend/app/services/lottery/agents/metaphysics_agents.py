"""Metaphysics-oriented lottery strategy agents."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ChartProfile, PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .helpers import energy_similarity, rank_scores, recent_history, select_numbers


GROUP = "metaphysics"
GRAPH_HIGHLIGHT_LIMIT = 6
STEM_BRANCH_WINDOW = 240
GRAPH_WINDOW = 180
CHART_WINDOW = 120
STEM_BRANCH_WEIGHT = 1.0
GRAPH_WEIGHT = 0.25
SIMILARITY_WEIGHT = 1.8
CHART_WEIGHT = 3.0


def _chart_lookup(context: PredictionContext) -> dict[str, ChartProfile]:
    lookup = {}
    for chart in context.chart_profiles:
        period = str(chart.metadata.get("period", "")).strip()
        if period:
            lookup[period] = chart
    return lookup


def _graph_weight(context: PredictionContext, draw_terms: tuple[str, ...]) -> float:
    scores = context.graph_snapshot.concept_scores
    return sum(float(scores.get(term, 0.0)) for term in draw_terms)


def _terms_for_draw(draw) -> tuple[str, ...]:
    return (
        *draw.daily_energy.mutagen,
        *draw.hourly_energy.mutagen,
        draw.daily_energy.stem,
        draw.daily_energy.branch,
        draw.hourly_energy.stem,
        draw.hourly_energy.branch,
    )


def _chart_terms(chart: ChartProfile | None, draw) -> tuple[str, ...]:
    if chart and chart.feature_terms:
        return chart.feature_terms
    return _terms_for_draw(draw)


def _stem_branch_component(context: PredictionContext) -> dict[int, float]:
    segment = recent_history(context.history_draws, STEM_BRANCH_WINDOW)
    total = len(segment)
    scores = {number: 0.0 for number in range(1, 81)}
    for index, draw in enumerate(segment, start=1):
        draw_score = 0.0
        draw_score += 3.0 * (draw.daily_energy.stem == context.target_draw.daily_energy.stem)
        draw_score += 3.0 * (draw.daily_energy.branch == context.target_draw.daily_energy.branch)
        draw_score += 2.0 * (draw.hourly_energy.stem == context.target_draw.hourly_energy.stem)
        draw_score += 2.0 * (draw.hourly_energy.branch == context.target_draw.hourly_energy.branch)
        if draw_score <= 0:
            continue
        factor = 1.0 + (index / max(total, 1)) * 0.35
        for number in draw.numbers:
            scores[number] += draw_score * factor * STEM_BRANCH_WEIGHT
    return scores


def _graph_component(context: PredictionContext) -> dict[int, float]:
    segment = recent_history(context.history_draws, GRAPH_WINDOW)
    scores = {number: 0.0 for number in range(1, 81)}
    for draw in segment:
        resonance = _graph_weight(context, _terms_for_draw(draw))
        similarity = energy_similarity(draw, context.target_draw)
        total_score = resonance * GRAPH_WEIGHT + similarity * SIMILARITY_WEIGHT
        if total_score <= 0:
            continue
        for number in draw.numbers:
            scores[number] += total_score
    return scores


def _chart_component(context: PredictionContext) -> dict[int, float]:
    scores = {number: 0.0 for number in range(1, 81)}
    if not context.chart_profiles:
        return scores
    segment = recent_history(context.history_draws, CHART_WINDOW)
    lookup = _chart_lookup(context)
    target_terms = _chart_terms(lookup.get(context.target_draw.period), context.target_draw)
    for draw in segment:
        draw_terms = _chart_terms(lookup.get(draw.period), draw)
        overlap = len(set(draw_terms) & set(target_terms))
        chart_score = overlap * CHART_WEIGHT
        if chart_score <= 0:
            continue
        similarity = energy_similarity(draw, context.target_draw)
        for number in draw.numbers:
            scores[number] += chart_score + similarity
    return scores


def _merge_scores(*parts: dict[int, float]) -> dict[int, float]:
    scores = {number: 0.0 for number in range(1, 81)}
    for part in parts:
        for number, value in part.items():
            scores[number] += value
    return scores


@dataclass(frozen=True)
class MetaphysicsFusedBoardAgent(StrategyAgent):
    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        stem_branch_scores = _stem_branch_component(context)
        graph_scores = _graph_component(context)
        chart_scores = _chart_component(context)
        scores = _merge_scores(stem_branch_scores, graph_scores, chart_scores)
        highlights = context.graph_snapshot.highlights[:GRAPH_HIGHLIGHT_LIMIT]
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=(
                "Fuse stem-branch matches, chart mapping, and graph resonance into one board. "
                f"Highlights: {', '.join(highlights) or 'none'}."
            ),
            ranked_scores=rank_scores(scores, pick_size),
            metadata={"graph_snapshot": context.graph_snapshot.snapshot_id},
        )


def build_metaphysics_agents(chart_count: int) -> dict[str, StrategyAgent]:
    required_history = max(STEM_BRANCH_WINDOW, GRAPH_WINDOW)
    if chart_count > 0:
        required_history = max(required_history, CHART_WINDOW)
    agent = MetaphysicsFusedBoardAgent(
        "metaphysics_fused_board",
        "Metaphysics Fused Board",
        "Fuse stem-branch, chart mapping, and graph resonance.",
        required_history,
        GROUP,
    )
    return {agent.strategy_id: agent}
