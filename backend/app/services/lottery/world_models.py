"""Structured models for lottery world sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping
import uuid


def world_now() -> str:
    return datetime.now(UTC).isoformat()


def world_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class WorldAgentRef:
    session_agent_id: str
    display_name: str
    role_kind: str
    group: str
    letta_agent_id: str
    strategy_id: str | None = None
    description: str = ""
    execution_binding: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorldEvent:
    event_id: str
    session_id: str
    period: str
    phase: str
    event_type: str
    actor_id: str
    actor_display_name: str
    content: str
    created_at: str
    numbers: tuple[int, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorldSession:
    session_id: str
    runtime_mode: str
    status: str
    pick_size: int
    budget_yuan: int
    selected_strategy_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    world_goal: str
    current_phase: str = "idle"
    current_period: str | None = None
    visible_through_period: str | None = None
    game_id: str = "happy8"
    active_agent_ids: tuple[str, ...] = ()
    shared_memory: Mapping[str, str] = field(default_factory=dict)
    agent_block_schema_version: int = 0
    agents: tuple[WorldAgentRef, ...] = ()
    agent_state: Mapping[str, Any] = field(default_factory=dict)
    execution_overrides: Mapping[str, Any] = field(default_factory=dict)
    resolved_execution_bindings: Mapping[str, Any] = field(default_factory=dict)
    feature_profile: Mapping[str, Any] = field(default_factory=dict)
    request_metrics: Mapping[str, Any] = field(default_factory=dict)
    progress: Mapping[str, Any] = field(default_factory=dict)
    round_history: tuple[Mapping[str, Any], ...] = ()
    settlement_history: tuple[Mapping[str, Any], ...] = ()
    issue_ledger: tuple[Mapping[str, Any], ...] = ()
    current_round: Mapping[str, Any] = field(default_factory=dict)
    latest_prediction: Mapping[str, Any] = field(default_factory=dict)
    latest_purchase_plan: Mapping[str, Any] = field(default_factory=dict)
    latest_review: Mapping[str, Any] = field(default_factory=dict)
    latest_issue_summary: Mapping[str, Any] = field(default_factory=dict)
    asset_manifest: tuple[Mapping[str, Any], ...] = ()
    execution_log: tuple[Mapping[str, Any], ...] = ()
    failed_phase: str | None = None
    last_success_phase: str | None = None
    error: Mapping[str, Any] | None = None
    report_artifacts: Mapping[str, Any] | None = None
    llm_model_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["agents"] = [item.to_dict() for item in self.agents]
        return payload

    @classmethod
    def create(
        cls,
        runtime_mode: str,
        pick_size: int,
        budget_yuan: int,
        selected_strategy_ids: list[str],
        world_goal: str,
        llm_model_name: str | None = None,
        game_id: str = "happy8",
        session_id: str | None = None,
    ) -> "WorldSession":
        now = world_now()
        return cls(
            session_id=session_id or world_id("world"),
            runtime_mode=runtime_mode,
            status="idle",
            pick_size=pick_size,
            budget_yuan=budget_yuan,
            selected_strategy_ids=tuple(selected_strategy_ids),
            created_at=now,
            updated_at=now,
            world_goal=world_goal,
            llm_model_name=llm_model_name,
            game_id=game_id,
        )
