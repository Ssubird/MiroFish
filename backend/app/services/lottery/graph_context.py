"""Local Ziwei domain graph construction."""

from __future__ import annotations

from collections import Counter
import hashlib

from .constants import GRAPH_RECENT_DRAW_LIMIT
from .models import ChartProfile, DrawRecord, GraphEdge, GraphNode, GraphSnapshot, KnowledgeDocument


class DomainGraphService:
    """Build compact local graph snapshots from books, charts, and draw energy."""

    def build_workspace_graph(
        self,
        knowledge_documents: list[KnowledgeDocument],
        chart_profiles: list[ChartProfile],
        completed_draws: list[DrawRecord],
        pending_draw: DrawRecord | None,
    ) -> GraphSnapshot:
        draws = completed_draws[-GRAPH_RECENT_DRAW_LIMIT:]
        return self._build_snapshot("workspace", draws, pending_draw, knowledge_documents, chart_profiles)

    def build_prediction_graph(
        self,
        history_draws: list[DrawRecord],
        target_draw: DrawRecord,
        knowledge_documents: list[KnowledgeDocument],
        chart_profiles: list[ChartProfile],
    ) -> GraphSnapshot:
        draws = history_draws[-GRAPH_RECENT_DRAW_LIMIT:]
        return self._build_snapshot("prediction", draws, target_draw, knowledge_documents, chart_profiles)

    def to_text(self, snapshot: GraphSnapshot) -> str:
        lines = [
            f"图谱快照: {snapshot.snapshot_id}",
            f"节点数: {snapshot.node_count}",
            f"边数: {snapshot.edge_count}",
            f"图谱高频概念: {', '.join(snapshot.highlights[:8]) or '无'}",
        ]
        if snapshot.chart_count:
            lines.append(f"命盘文件数: {snapshot.chart_count}")
        if snapshot.preview_relations:
            lines.append("关键关系:")
            lines.extend(f"- {item}" for item in snapshot.preview_relations[:6])
        return "\n".join(lines)

    def _build_snapshot(
        self,
        prefix: str,
        history_draws: list[DrawRecord],
        target_draw: DrawRecord | None,
        knowledge_documents: list[KnowledgeDocument],
        chart_profiles: list[ChartProfile],
    ) -> GraphSnapshot:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        concept_scores = Counter()
        doc_names = []

        for document in knowledge_documents:
            node_id = f"doc:{document.relative_path}"
            nodes.append(GraphNode(node_id=node_id, kind=document.kind, name=document.name))
            doc_names.append(document.name)
            for term in document.terms:
                concept_scores[term] += 2.0
                edges.append(GraphEdge(source_id=node_id, target_id=f"concept:{term}", relation="MENTIONS"))

        for chart in chart_profiles:
            node_id = f"chart:{chart.relative_path}"
            nodes.append(GraphNode(node_id=node_id, kind=chart.kind, name=chart.name))
            for term in chart.feature_terms:
                concept_scores[term] += 3.0
                edges.append(GraphEdge(source_id=node_id, target_id=f"concept:{term}", relation="CHART_HAS"))

        if history_draws:
            history_node = GraphNode(node_id=f"{prefix}:history", kind="history", name="history_window")
            nodes.append(history_node)
            for term in self._draw_terms(history_draws):
                concept_scores[term] += 1.0
                edges.append(GraphEdge(source_id=history_node.node_id, target_id=f"concept:{term}", relation="HISTORY_SUPPORTS"))

        if target_draw:
            target_node = GraphNode(node_id=f"{prefix}:target:{target_draw.period}", kind="target", name=target_draw.period)
            nodes.append(target_node)
            for term in self._draw_terms([target_draw]):
                concept_scores[term] += 4.0
                edges.append(GraphEdge(source_id=target_node.node_id, target_id=f"concept:{term}", relation="TARGET_FOCUSES"))

        top_concepts = [term for term, _ in concept_scores.most_common(12)]
        concept_nodes = [GraphNode(node_id=f"concept:{term}", kind="concept", name=term) for term in top_concepts]
        nodes.extend(concept_nodes)
        preview = [f"{edge.source_id} --{edge.relation}--> {edge.target_id}" for edge in edges[:12]]
        snapshot_id = self._snapshot_id(prefix, history_draws, target_draw, top_concepts)
        return GraphSnapshot(
            snapshot_id=snapshot_id,
            node_count=len(nodes),
            edge_count=len(edges),
            highlights=tuple(top_concepts),
            concept_scores=dict(concept_scores),
            source_documents=tuple(doc_names),
            chart_count=len(chart_profiles),
            preview_relations=tuple(preview),
            provider="local",
        )

    def _draw_terms(self, draws: list[DrawRecord]) -> tuple[str, ...]:
        terms = []
        for draw in draws:
            terms.extend(draw.daily_energy.mutagen)
            terms.extend(draw.hourly_energy.mutagen)
            terms.append(draw.daily_energy.stem)
            terms.append(draw.daily_energy.branch)
            terms.append(draw.hourly_energy.stem)
            terms.append(draw.hourly_energy.branch)
        return tuple(terms)

    def _snapshot_id(
        self,
        prefix: str,
        history_draws: list[DrawRecord],
        target_draw: DrawRecord | None,
        top_concepts: list[str],
    ) -> str:
        parts = [prefix, *(draw.period for draw in history_draws[-3:]), target_draw.period if target_draw else "none", *top_concepts[:4]]
        digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"
