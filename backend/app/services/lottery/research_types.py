"""Shared immutable types for lottery research service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .agents import StrategyAgent
from .models import ChartProfile, DrawRecord, GraphSnapshot, KnowledgeDocument, StrategyPrediction


@dataclass(frozen=True)
class WorkspaceAssets:
    completed_draws: tuple[DrawRecord, ...]
    pending_draws: tuple[DrawRecord, ...]
    knowledge_documents: tuple[KnowledgeDocument, ...]
    chart_profiles: tuple[ChartProfile, ...]
    strategies: dict[str, StrategyAgent]
    local_workspace_graph: GraphSnapshot
    kuzu_graph_status: dict[str, object]
    zep_graph_status: dict[str, object]


@dataclass(frozen=True)
class LLMRunOptions:
    request_delay_ms: int
    model_name: str | None
    retry_count: int
    retry_backoff_ms: int
    parallelism: int
    issue_parallelism: int
    agent_dialogue_enabled: bool
    agent_dialogue_rounds: int
    graph_mode: str
    zep_graph_id: str | None
    runtime_mode: str
    warmup_size: int
    live_interview_enabled: bool
    budget_yuan: int
    session_id: str | None = None
    execution_overrides: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IssueReplay:
    target_draw: DrawRecord
    predictions: dict[str, StrategyPrediction]


@dataclass(frozen=True)
class WindowBacktest:
    issue_results: dict[str, list[dict[str, object]]]
    issue_replays: tuple[IssueReplay, ...]
    warmup_replays: tuple[IssueReplay, ...] = ()
    warmup_size: int = 0
    social_state: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    world_state: Mapping[str, Any] = field(default_factory=dict)
