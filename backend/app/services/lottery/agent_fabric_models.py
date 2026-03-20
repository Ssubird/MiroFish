"""Data models for declarative world_v2 agent fabric specs."""

from __future__ import annotations

from dataclasses import field, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PromptBlockSpec:
    block_type: str
    title: str = ""
    text: str = ""
    path: str = ""
    name: str = ""
    key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.block_type,
            "title": self.title,
            "text": self.text,
            "path": self.path,
            "name": self.name,
            "key": self.key,
        }


@dataclass(frozen=True)
class DialoguePolicy:
    mode: str = "disabled"
    rounds: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rounds": self.rounds,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PhaseSpec:
    phase_id: str
    active_groups: tuple[str, ...] = ()
    default_profile_id: str | None = None
    visible_groups: tuple[str, ...] = ()
    shared_memory_keys: tuple[str, ...] = ()
    prompt_blocks: tuple[PromptBlockSpec, ...] = ()
    limits: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "active_groups": list(self.active_groups),
            "default_profile_id": self.default_profile_id,
            "visible_groups": list(self.visible_groups),
            "shared_memory_keys": list(self.shared_memory_keys),
            "prompt_blocks": [item.to_dict() for item in self.prompt_blocks],
            "limits": dict(self.limits),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GroupSpec:
    group_id: str
    role_kind: str
    default_profile_id: str | None = None
    visible_groups: tuple[str, ...] = ()
    shared_memory_keys: tuple[str, ...] = ()
    prompt_blocks: tuple[PromptBlockSpec, ...] = ()
    limits: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "role_kind": self.role_kind,
            "default_profile_id": self.default_profile_id,
            "visible_groups": list(self.visible_groups),
            "shared_memory_keys": list(self.shared_memory_keys),
            "prompt_blocks": [item.to_dict() for item in self.prompt_blocks],
            "limits": dict(self.limits),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    description: str
    behavior_template: str
    role_kind: str
    group: str
    phases: tuple[str, ...]
    profile_id: str | None = None
    prompt_blocks: tuple[PromptBlockSpec, ...] = ()
    document_refs: tuple[str, ...] = ()
    shared_memory_keys: tuple[str, ...] = ()
    visible_groups: tuple[str, ...] = ()
    visible_agents: tuple[str, ...] = ()
    dialogue_policy: DialoguePolicy = field(default_factory=DialoguePolicy)
    limits: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "description": self.description,
            "behavior_template": self.behavior_template,
            "role_kind": self.role_kind,
            "group": self.group,
            "phases": list(self.phases),
            "profile_id": self.profile_id,
            "prompt_blocks": [item.to_dict() for item in self.prompt_blocks],
            "document_refs": list(self.document_refs),
            "shared_memory_keys": list(self.shared_memory_keys),
            "visible_groups": list(self.visible_groups),
            "visible_agents": list(self.visible_agents),
            "dialogue_policy": self.dialogue_policy.to_dict(),
            "limits": dict(self.limits),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResolvedAgentSpec:
    agent_id: str
    display_name: str
    description: str
    behavior_template: str
    role_kind: str
    group: str
    phases: tuple[str, ...]
    profile_id: str | None
    prompt_blocks: tuple[PromptBlockSpec, ...]
    document_refs: tuple[str, ...]
    shared_memory_keys: tuple[str, ...]
    visible_groups: tuple[str, ...]
    visible_agents: tuple[str, ...]
    dialogue_policy: DialoguePolicy
    limits: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "description": self.description,
            "behavior_template": self.behavior_template,
            "role_kind": self.role_kind,
            "group": self.group,
            "phases": list(self.phases),
            "profile_id": self.profile_id,
            "prompt_blocks": [item.to_dict() for item in self.prompt_blocks],
            "document_refs": list(self.document_refs),
            "shared_memory_keys": list(self.shared_memory_keys),
            "visible_groups": list(self.visible_groups),
            "visible_agents": list(self.visible_agents),
            "dialogue_policy": self.dialogue_policy.to_dict(),
            "limits": dict(self.limits),
            "metadata": dict(self.metadata),
        }
