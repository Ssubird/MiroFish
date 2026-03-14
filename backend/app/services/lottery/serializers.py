"""Serialization helpers for lottery research responses."""

from __future__ import annotations

from collections import defaultdict

from .models import ChartProfile, DrawRecord, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from .report_scope import report_scope


def serialize_draw_head(draw: DrawRecord) -> dict[str, object]:
    return {
        "period": draw.period,
        "date": draw.date,
        "has_numbers": draw.has_numbers,
        "numbers_count": len(draw.numbers),
    }


def serialize_optional_draw(draws: tuple[DrawRecord, ...]) -> dict[str, object] | None:
    return serialize_draw_head(draws[-1]) if draws else None


def serialize_document(document: KnowledgeDocument) -> dict[str, object]:
    payload = {
        "name": document.name,
        "kind": document.kind,
        "path": document.relative_path,
        "char_count": document.char_count,
        "term_count": len(document.terms),
    }
    if document.kind == "report":
        payload["report_scope"] = report_scope(document)
    return payload


def serialize_chart(chart: ChartProfile) -> dict[str, object]:
    return {
        "name": chart.name,
        "kind": chart.kind,
        "path": chart.relative_path,
        "char_count": chart.char_count,
        "term_count": len(chart.feature_terms),
    }


def serialize_graph(snapshot: GraphSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "provider": snapshot.provider,
        "backend_graph_id": snapshot.backend_graph_id,
        "query": snapshot.query,
        "node_count": snapshot.node_count,
        "edge_count": snapshot.edge_count,
        "chart_count": snapshot.chart_count,
        "highlights": list(snapshot.highlights),
        "preview_relations": list(snapshot.preview_relations[:6]),
    }


def serialize_strategy(strategy) -> dict[str, object]:
    return {
        "strategy_id": strategy.strategy_id,
        "display_name": strategy.display_name,
        "description": strategy.description,
        "group": strategy.group,
        "required_history": strategy.required_history,
        "kind": strategy.kind,
        "uses_llm": strategy.uses_llm,
        "supports_dialogue": getattr(strategy, "supports_dialogue", False),
        "default_enabled": strategy.default_enabled,
    }


def serialize_prediction(prediction: StrategyPrediction, metrics: dict[str, object], preview_limit: int) -> dict[str, object]:
    return {
        "strategy_id": prediction.strategy_id,
        "display_name": prediction.display_name,
        "group": prediction.group,
        "backtest_average_hits": round(float(metrics.get("average_hits", 0.0)), 4),
        "backtest_objective_score": round(float(metrics.get("objective_score", 0.0)), 4),
        "backtest_strategy_roi": round(float(metrics.get("strategy_roi", 0.0)), 4),
        "numbers": list(prediction.numbers),
        "rationale": prediction.rationale,
        "kind": prediction.kind,
        "metadata": prediction.metadata,
        "ranked_scores": [
            {"number": number, "score": round(score, 4)}
            for number, score in prediction.ranked_scores[:preview_limit]
        ],
    }


def summarize_documents(documents: tuple[KnowledgeDocument, ...]) -> dict[str, object]:
    summary = defaultdict(int)
    for item in documents:
        summary[item.kind] += 1
    return {"total_documents": len(documents), "by_kind": dict(sorted(summary.items()))}


def summarize_charts(charts: tuple[ChartProfile, ...]) -> dict[str, object]:
    return {
        "total_charts": len(charts),
        "with_terms": len([chart for chart in charts if chart.feature_terms]),
    }
