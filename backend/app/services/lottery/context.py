"""Prediction context construction for isolated backtests."""

from __future__ import annotations

from dataclasses import replace

from .expert_interviews import build_expert_interviews
from .graph_context import DomainGraphService
from .models import ChartProfile, DrawRecord, KnowledgeDocument, PredictionContext, StrategyPrediction


def build_prediction_context(
    history_draws: list[DrawRecord],
    target_draw: DrawRecord,
    knowledge_documents: list[KnowledgeDocument],
    chart_profiles: list[ChartProfile],
    graph_service: DomainGraphService | None = None,
    graph_snapshot=None,
    llm_request_delay_ms: int = 0,
    llm_model_name: str | None = None,
    llm_retry_count: int = 0,
    llm_retry_backoff_ms: int = 0,
    strategy_performance: dict[str, dict[str, object]] | None = None,
    optimization_goal: str = "联合优化直接命中、策略 ROI、稳定性惩罚与过热惩罚。",
    social_state: dict[str, dict[str, object]] | None = None,
    world_state: dict[str, object] | None = None,
) -> PredictionContext:
    visible_charts = _visible_chart_profiles(history_draws, target_draw, chart_profiles)
    active_snapshot = graph_snapshot
    if active_snapshot is None:
        if graph_service is None:
            raise ValueError("graph_service 与 graph_snapshot 不能同时为空")
        active_snapshot = graph_service.build_prediction_graph(
            history_draws=history_draws,
            target_draw=target_draw,
            knowledge_documents=knowledge_documents,
            chart_profiles=visible_charts,
        )
    return PredictionContext(
        history_draws=tuple(history_draws),
        target_draw=target_draw,
        knowledge_documents=tuple(knowledge_documents),
        chart_profiles=tuple(visible_charts),
        graph_snapshot=active_snapshot,
        llm_request_delay_ms=llm_request_delay_ms,
        llm_model_name=llm_model_name,
        llm_retry_count=llm_retry_count,
        llm_retry_backoff_ms=llm_retry_backoff_ms,
        strategy_performance=strategy_performance or {},
        optimization_goal=optimization_goal,
        social_state=social_state or {},
        world_state=world_state or {},
    )


def attach_peer_predictions(
    context: PredictionContext,
    predictions: dict[str, StrategyPrediction],
) -> PredictionContext:
    return replace(
        context,
        peer_numbers={key: value.numbers for key, value in predictions.items()},
        peer_predictions={
            key: {
                "display_name": value.display_name,
                "group": value.group,
                "kind": value.kind,
                "numbers": list(value.numbers),
                "rationale": value.rationale,
                "metadata": dict(value.metadata or {}),
            }
            for key, value in predictions.items()
        },
    )


def attach_expert_interviews(
    context: PredictionContext,
    predictions: dict[str, StrategyPrediction],
) -> PredictionContext:
    return replace(context, expert_interviews=build_expert_interviews(context, predictions))


def _visible_chart_profiles(
    history_draws: list[DrawRecord],
    target_draw: DrawRecord,
    chart_profiles: list[ChartProfile],
) -> list[ChartProfile]:
    visible_periods = {draw.period for draw in history_draws}
    visible_periods.add(target_draw.period)
    visible = []
    for chart in chart_profiles:
        period = str(chart.metadata.get("period", "")).strip()
        if not period or period in visible_periods:
            visible.append(chart)
    return visible
