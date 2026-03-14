"""Knowledge retrieval helpers for graph-grounded LLM lottery agents."""

from __future__ import annotations

from dataclasses import dataclass

from .models import PredictionContext


KNOWLEDGE_LIMIT = 3
PROMPT_LIMIT = 1
REPORT_LIMIT = 2
CHART_LIMIT = 2
EXCERPT_CHARS = 900
TARGET_CHART_BONUS = 6.0
HISTORY_CHART_BONUS = 2.0


@dataclass(frozen=True)
class KnowledgeSnippet:
    """Prompt grounding unit assembled from workspace assets."""

    source: str
    kind: str
    excerpt: str
    score: float


class KnowledgeContextBuilder:
    """Select the most relevant docs, reports, and charts for one issue."""

    def build(self, context: PredictionContext) -> list[KnowledgeSnippet]:
        snippets = []
        snippets.extend(self._document_snippets(context, "knowledge", KNOWLEDGE_LIMIT))
        snippets.extend(self._document_snippets(context, "prompt", PROMPT_LIMIT))
        snippets.extend(self._document_snippets(context, "report", REPORT_LIMIT))
        snippets.extend(self._chart_snippets(context))
        snippets.append(self._graph_snippet(context))
        return snippets

    def _document_snippets(
        self,
        context: PredictionContext,
        kind: str,
        limit: int,
    ) -> list[KnowledgeSnippet]:
        docs = [item for item in context.knowledge_documents if item.kind == kind]
        ranked = sorted(docs, key=lambda item: (-self._score_terms(item.terms, context), item.name))
        return [self._document_snippet(item, self._score_terms(item.terms, context)) for item in ranked[:limit]]

    def _chart_snippets(self, context: PredictionContext) -> list[KnowledgeSnippet]:
        ranked = sorted(
            context.chart_profiles,
            key=lambda item: (-self._score_chart(item, context), item.name),
        )
        return [self._chart_snippet(item, self._score_chart(item, context)) for item in ranked[:CHART_LIMIT]]

    def _graph_snippet(self, context: PredictionContext) -> KnowledgeSnippet:
        snapshot = context.graph_snapshot
        excerpt = (
            f"graph={snapshot.snapshot_id}\n"
            f"provider={snapshot.provider}\n"
            f"graph_id={snapshot.backend_graph_id or 'local'}\n"
            f"highlights={', '.join(snapshot.highlights[:10])}\n"
            f"relations={'; '.join(snapshot.preview_relations[:6])}"
        )
        return KnowledgeSnippet("workspace_graph", "graph", excerpt, 9.0)

    def _document_snippet(self, document, score: float) -> KnowledgeSnippet:
        excerpt = document.content.strip()[:EXCERPT_CHARS]
        return KnowledgeSnippet(document.name, document.kind, excerpt, score)

    def _chart_snippet(self, chart, score: float) -> KnowledgeSnippet:
        excerpt = chart.content.strip()[:EXCERPT_CHARS]
        return KnowledgeSnippet(chart.name, chart.kind, excerpt, score)

    def _score_chart(self, chart, context: PredictionContext) -> float:
        score = self._score_terms(chart.feature_terms, context)
        period = str(chart.metadata.get("period", "")).strip()
        if period == context.target_draw.period:
            return score + TARGET_CHART_BONUS
        history_periods = {draw.period for draw in context.history_draws[-12:]}
        if period in history_periods:
            return score + HISTORY_CHART_BONUS
        return score

    def _score_terms(self, terms: tuple[str, ...], context: PredictionContext) -> float:
        target_terms = {
            context.target_draw.daily_energy.stem,
            context.target_draw.daily_energy.branch,
            context.target_draw.hourly_energy.stem,
            context.target_draw.hourly_energy.branch,
            *context.target_draw.daily_energy.mutagen,
            *context.target_draw.hourly_energy.mutagen,
            *context.graph_snapshot.highlights[:10],
        }
        return float(sum(2.0 for term in terms if term in target_terms))
