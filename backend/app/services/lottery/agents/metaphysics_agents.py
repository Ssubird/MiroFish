"""Metaphysics-oriented lottery strategy agents."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ChartProfile, PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .helpers import energy_similarity, rank_scores, recent_history, select_numbers


GROUP = "metaphysics"
GRAPH_HIGHLIGHT_LIMIT = 6


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


@dataclass(frozen=True)
class StemBranchMatchAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        scores = {number: 0.0 for number in range(1, 81)}
        total = len(segment)
        for index, draw in enumerate(segment, start=1):
            draw_score = 0.0
            draw_score += 3.0 * (draw.daily_energy.stem == context.target_draw.daily_energy.stem)
            draw_score += 3.0 * (draw.daily_energy.branch == context.target_draw.daily_energy.branch)
            draw_score += 2.0 * (draw.hourly_energy.stem == context.target_draw.hourly_energy.stem)
            draw_score += 2.0 * (draw.hourly_energy.branch == context.target_draw.hourly_energy.branch)
            if draw_score <= 0:
                continue
            factor = 1.0 + (index / total) * 0.35
            for number in draw.numbers:
                scores[number] += draw_score * factor
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"按最近 {self.window} 期干支结构的相近度回看历史开奖。",
            ranked_scores=rank_scores(scores, pick_size),
        )


@dataclass(frozen=True)
class GraphResonanceAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        segment = recent_history(context.history_draws, self.window)
        scores = {number: 0.0 for number in range(1, 81)}
        highlights = context.graph_snapshot.highlights[:GRAPH_HIGHLIGHT_LIMIT]
        for draw in segment:
            resonance = _graph_weight(context, _terms_for_draw(draw))
            similarity = energy_similarity(draw, context.target_draw)
            total_score = resonance * 0.25 + similarity * 1.8
            if total_score <= 0:
                continue
            for number in draw.numbers:
                scores[number] += total_score
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale=f"把本地图谱高频概念 {', '.join(highlights) or '无'} 与能量相似样本一起加权。",
            ranked_scores=rank_scores(scores, pick_size),
            metadata={"graph_snapshot": context.graph_snapshot.snapshot_id},
        )


@dataclass(frozen=True)
class ChartSignatureAgent(StrategyAgent):
    window: int

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        if not context.chart_profiles:
            raise ValueError(f"{self.display_name} 需要命盘数据文件")
        segment = recent_history(context.history_draws, self.window)
        lookup = _chart_lookup(context)
        target_terms = _chart_terms(lookup.get(context.target_draw.period), context.target_draw)
        scores = {number: 0.0 for number in range(1, 81)}
        for draw in segment:
            draw_terms = _chart_terms(lookup.get(draw.period), draw)
            overlap = len(set(draw_terms) & set(target_terms))
            chart_score = overlap * 3.0
            if chart_score <= 0:
                continue
            similarity = energy_similarity(draw, context.target_draw)
            for number in draw.numbers:
                scores[number] += chart_score + similarity
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=select_numbers(scores, pick_size),
            rationale="直接比对 draw 文件里的历史命盘与目标期命盘，再聚合对应历史号码。",
            ranked_scores=rank_scores(scores, pick_size),
            metadata={"chart_count": len(context.chart_profiles)},
        )


def build_metaphysics_agents(chart_count: int) -> dict[str, StrategyAgent]:
    agents = [
        StemBranchMatchAgent("stem_branch_240", "干支匹配-240期", "用目标期干支映射相似历史样本。", 240, GROUP, window=240),
        GraphResonanceAgent("graph_resonance_180", "图谱共振-180期", "让紫微书与命盘图谱参与号码打分。", 180, GROUP, window=180),
    ]
    if chart_count > 0:
        agents.append(
            ChartSignatureAgent("chart_signature_120", "命盘映射-120期", "用命盘特征和目标期能量共同筛样本。", 120, GROUP, window=120)
        )
    return {agent.strategy_id: agent for agent in agents}
