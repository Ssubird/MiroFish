"""Immutable models for lottery research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class EnergySignature:
    """Daily or hourly Ziwei energy markers."""

    stem: str
    branch: str
    mutagen: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "EnergySignature":
        payload = data or {}
        mutagen = tuple(str(item) for item in payload.get("mutagen", []))
        return cls(
            stem=str(payload.get("stem", "")),
            branch=str(payload.get("branch", "")),
            mutagen=mutagen,
        )


@dataclass(frozen=True)
class DrawRecord:
    """A single Keno8 draw enriched with Ziwei metadata."""

    period: str
    date: str
    chinese_date: str
    numbers: tuple[int, ...]
    daily_energy: EnergySignature
    hourly_energy: EnergySignature

    @property
    def has_numbers(self) -> bool:
        return bool(self.numbers)


@dataclass(frozen=True)
class KnowledgeDocument:
    """Metadata and content for a knowledge source."""

    name: str
    kind: str
    relative_path: str
    char_count: int
    content: str
    terms: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChartProfile:
    """Structured or semi-structured chart content."""

    name: str
    kind: str
    relative_path: str
    char_count: int
    content: str
    feature_terms: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphNode:
    """A node in the local Ziwei domain graph."""

    node_id: str
    kind: str
    name: str


@dataclass(frozen=True)
class GraphEdge:
    """A relationship in the local Ziwei domain graph."""

    source_id: str
    target_id: str
    relation: str


@dataclass(frozen=True)
class GraphSnapshot:
    """A compact graph snapshot for prompting and UI inspection."""

    snapshot_id: str
    node_count: int
    edge_count: int
    highlights: tuple[str, ...]
    concept_scores: Mapping[str, float]
    source_documents: tuple[str, ...]
    chart_count: int
    preview_relations: tuple[str, ...]
    provider: str = "local"
    backend_graph_id: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class PredictionContext:
    """The only data surface visible to strategy agents."""

    history_draws: tuple[DrawRecord, ...]
    target_draw: DrawRecord
    knowledge_documents: tuple[KnowledgeDocument, ...]
    chart_profiles: tuple[ChartProfile, ...]
    graph_snapshot: GraphSnapshot
    llm_request_delay_ms: int = 0
    llm_model_name: str | None = None
    llm_retry_count: int = 0
    llm_retry_backoff_ms: int = 0
    strategy_performance: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    optimization_goal: str = "联合优化直接命中、策略 ROI、稳定性惩罚与过热惩罚。"
    peer_numbers: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    peer_predictions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    social_state: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    expert_interviews: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    world_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyPrediction:
    """Prediction produced by a strategy agent."""

    strategy_id: str
    display_name: str
    group: str
    numbers: tuple[int, ...]
    rationale: str
    ranked_scores: tuple[tuple[int, float], ...]
    kind: str = "rule"
    metadata: Mapping[str, Any] | None = None
