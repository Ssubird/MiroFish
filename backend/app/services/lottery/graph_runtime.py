"""Graph selection helpers for lottery runtime."""

from __future__ import annotations

from .constants import KUZU_GRAPH_MODE, LOCAL_GRAPH_MODE
from .document_filters import grounding_documents


def workspace_graph(graph_service, kuzu_graph_service, zep_graph_service, assets, options):
    target_draw = assets.pending_draws[-1] if assets.pending_draws else None
    documents = grounding_documents(assets.knowledge_documents, target_draw)
    if options.graph_mode == LOCAL_GRAPH_MODE:
        return assets.local_workspace_graph
    if options.graph_mode == KUZU_GRAPH_MODE:
        return kuzu_graph_service.build_workspace_graph(
            list(documents),
            list(assets.chart_profiles),
            list(assets.completed_draws),
            target_draw,
        )
    return zep_graph_service.build_workspace_graph(
        list(documents),
        list(assets.chart_profiles),
        list(assets.completed_draws),
        target_draw,
        options.zep_graph_id,
    )


def prediction_graph(graph_service, kuzu_graph_service, zep_graph_service, history, target_draw, assets, options):
    documents = grounding_documents(assets.knowledge_documents, target_draw)
    if options.graph_mode == LOCAL_GRAPH_MODE:
        return graph_service.build_prediction_graph(
            history,
            target_draw,
            list(documents),
            list(assets.chart_profiles),
        )
    if options.graph_mode == KUZU_GRAPH_MODE:
        return kuzu_graph_service.build_prediction_graph(
            history,
            target_draw,
            list(documents),
            list(assets.chart_profiles),
        )
    return zep_graph_service.build_prediction_graph(
        history,
        target_draw,
        list(documents),
        list(assets.chart_profiles),
        options.zep_graph_id,
    )
