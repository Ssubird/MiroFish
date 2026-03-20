"""Immutable data models for the per-agent execution fabric.

Three-level override chain: system default → group override → agent override.
All bindings are declared in execution_config.yaml, never auto-selected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderSpec:
    """A registered LLM provider endpoint."""

    provider_id: str
    kind: str  # "openai_compatible" | "anthropic" | "ollama"
    base_url: str | None = None
    api_key_env: str | None = None  # env-var name, never a plaintext secret
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    timeout_s: int = 120


@dataclass(frozen=True)
class ModelSpec:
    """A model available under a specific provider."""

    model_id: str
    provider_id: str
    capability_tags: tuple[str, ...] = ()
    supports_json_mode: bool = False
    max_context: int | None = None
    cost_hint: str | None = None  # "cheap" | "medium" | "expensive"


@dataclass(frozen=True)
class ExecutionProfile:
    """A reusable execution-strategy template bound to a provider + model."""

    profile_id: str
    provider_id: str
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 2000
    json_mode: bool = False
    retry_count: int = 2
    retry_backoff_ms: int = 1500
    timeout_s: int = 120
    prompt_style: str = "strict_json"  # "strict_json" | "freeform" | "reasoned_json"
    fallback_profile_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentExecutionBinding:
    """Maps an agent to its primary execution profile."""

    agent_id: str
    primary_profile_id: str
    fallback_profile_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedExecutionBinding:
    """Materialized binding visible to runtime, reports, and UI."""

    agent_id: str
    role_kind: str
    group: str | None
    profile_id: str
    provider_id: str
    model_id: str
    temperature: float
    max_tokens: int
    json_mode: bool
    retry_count: int
    retry_backoff_ms: int
    timeout_s: int
    prompt_style: str
    fallback_profile_ids: tuple[str, ...] = ()
    routing_mode: str = "active"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fallback_profile_ids"] = list(self.fallback_profile_ids)
        payload["metadata"] = dict(self.metadata)
        return payload
