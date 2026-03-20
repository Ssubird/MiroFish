"""Declarative registry for world_v2 LLM agent fabric."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ...config import Config
from .agent_fabric_models import AgentSpec, DialoguePolicy, GroupSpec, PhaseSpec, PromptBlockSpec, ResolvedAgentSpec
from .agents.base import StrategyAgent
from .constants import PRIMARY_GROUPS
from .market_role_registry import PROMPT_ASSET_PASSAGE_CHAR_LIMIT, chunk_prompt_asset


SUPPORTED_ROLE_KINDS = ("social", "judge", "purchase", "decision")
BEHAVIOR_ROLE_MAP = {
    "social_discussion": "social",
    "judge_panel": "judge",
    "purchase_planner": "purchase",
    "final_decider": "decision",
}
SUPPORTED_BLOCK_TYPES = {"static_text", "prompt_file", "workspace_document", "workspace_file", "runtime_text", "shared_memory"}
SUPPORTED_DIALOGUE_MODES = {"disabled", "rounds", "single_pass"}
RUNTIME_VISIBLE_GROUPS = {*PRIMARY_GROUPS, "full_context", "social", "judge", "purchase", "decision"}
RUNTIME_BLOCKS = {
    "comment_schema": ("Runtime block", "comment_schema"),
    "debate_schema": ("Runtime block", "debate_schema"),
    "purchase_rule_block": ("Runtime block", "purchase_rule_block"),
    "purchase_schema": ("Runtime block", "purchase_schema"),
}


class AgentFabricConfigError(ValueError):
    """Raised when the agent fabric config is invalid."""


@dataclass(frozen=True)
class PromptAssetBundle:
    passages: tuple[str, ...]
    document_names: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class FabricStrategyAgent(StrategyAgent):
    behavior_template: str

    kind = "llm"
    uses_llm = True
    default_enabled = True
    supports_dialogue = True

    def predict(self, context, pick_size: int):
        raise NotImplementedError(f"{self.strategy_id} is a world_v2 declarative role and cannot run isolated predict()")


class AgentFabricRegistry:
    def __init__(self, root: Path | None = None, execution_registry=None) -> None:
        self.root = (root or Path(Config.AGENT_FABRIC_ROOT)).resolve()
        self.execution_registry = execution_registry
        self._prompt_root = self.root / "prompts"
        self._workspace_root = Path(Config.LOTTERY_DATA_ROOT).resolve()
        self._phases: dict[str, PhaseSpec] = {}
        self._groups: dict[str, GroupSpec] = {}
        self._agents: dict[str, AgentSpec] = {}
        self._passage_char_limit = PROMPT_ASSET_PASSAGE_CHAR_LIMIT
        self.reload()

    def reload(self) -> "AgentFabricRegistry":
        manifest = _read_yaml(self.root / "manifest.yaml")
        self._passage_char_limit = int(manifest.get("prompt_char_limit") or PROMPT_ASSET_PASSAGE_CHAR_LIMIT)
        self._phases = {item.phase_id: item for item in _parse_phases(manifest.get("phases"))}
        self._groups = {item.group_id: item for item in _parse_groups(manifest.get("groups"))}
        self._agents = _load_agents(self.root / "agents", self._groups, self._phases, self._prompt_root, self._profile_ids())
        _validate_block_files(self._prompt_root, self._workspace_root, [item.prompt_blocks for item in self._phases.values()])
        _validate_block_files(self._prompt_root, self._workspace_root, [item.prompt_blocks for item in self._groups.values()])
        _validate_block_files(self._prompt_root, self._workspace_root, [item.prompt_blocks for item in self._agents.values()])
        return self

    def phases(self) -> dict[str, PhaseSpec]:
        return dict(self._phases)

    def groups(self) -> dict[str, GroupSpec]:
        return dict(self._groups)

    def agents(self) -> dict[str, AgentSpec]:
        return dict(self._agents)

    def world_role_specs(self) -> tuple[ResolvedAgentSpec, ...]:
        return tuple(self.resolved_agent(item.agent_id) for item in self._agents.values() if item.role_kind in {"purchase", "decision"})

    def market_strategy_agents(self) -> dict[str, StrategyAgent]:
        rows = {}
        for item in self._agents.values():
            if item.role_kind not in {"social", "judge"}:
                continue
            rows[item.agent_id] = FabricStrategyAgent(
                item.agent_id,
                item.display_name,
                item.description,
                36,
                item.group,
                item.behavior_template,
            )
        return rows

    def phase_agent_ids(self, phase_id: str, group: str | None = None) -> list[str]:
        rows = []
        for item in self._agents.values():
            if phase_id not in item.phases:
                continue
            if group and item.group != group:
                continue
            rows.append(item.agent_id)
        return sorted(rows)

    def resolved_agent(self, agent_id: str) -> ResolvedAgentSpec:
        try:
            agent = self._agents[agent_id]
        except KeyError as exc:
            raise AgentFabricConfigError(f"Unknown agent fabric id: {agent_id}") from exc
        phase_specs = [self._phases[item] for item in agent.phases]
        group = self._groups[agent.group]
        return ResolvedAgentSpec(
            agent_id=agent.agent_id,
            display_name=agent.display_name,
            description=agent.description,
            behavior_template=agent.behavior_template,
            role_kind=agent.role_kind,
            group=agent.group,
            phases=agent.phases,
            profile_id=agent.profile_id or group.default_profile_id or _first_profile_id(phase_specs),
            prompt_blocks=_merge_prompt_blocks(*(item.prompt_blocks for item in phase_specs), group.prompt_blocks, agent.prompt_blocks),
            document_refs=_dedupe_text(*[() for _ in phase_specs], group.metadata.get("document_refs", ()), agent.document_refs),
            shared_memory_keys=_dedupe_text(*(item.shared_memory_keys for item in phase_specs), group.shared_memory_keys, agent.shared_memory_keys),
            visible_groups=_dedupe_text(*(item.visible_groups for item in phase_specs), group.visible_groups, agent.visible_groups),
            visible_agents=_dedupe_text(agent.visible_agents),
            dialogue_policy=agent.dialogue_policy,
            limits=_merge_mapping(*(item.limits for item in phase_specs), group.limits, agent.limits),
            metadata={**group.metadata, **agent.metadata},
        )

    def prompt_assets(
        self,
        agent_id: str,
        documents,
        shared_memory: Mapping[str, str] | None = None,
    ) -> PromptAssetBundle:
        spec = self.resolved_agent(agent_id)
        docs = _document_lookup(documents)
        passages: list[str] = []
        sources: list[dict[str, Any]] = []
        doc_names: list[str] = []
        order = 1
        for block in spec.prompt_blocks:
            chunk_rows, source = self._block_payload(block, docs, shared_memory or {}, order)
            passages.extend(chunk_rows)
            sources.append(source)
            if source["source_type"] in {"workspace_document", "workspace_file"}:
                doc_names.append(source["name"])
            order += 1
        for name in spec.document_refs:
            document = _required_document(docs, name)
            chunks = chunk_prompt_asset(document.name, document.content, "Workspace document", self._passage_char_limit)
            passages.extend(chunks)
            sources.append(_source_payload("workspace_document", document.name, order, chunks))
            doc_names.append(document.name)
            order += 1
        return PromptAssetBundle(tuple(passages), tuple(_dedupe_text(doc_names)), tuple(sources))

    def execution_overrides(self) -> dict[str, dict[str, str]]:
        return {
            "group_overrides": {},
            "agent_overrides": {
                item.agent_id: item.profile_id
                for item in (self.resolved_agent(agent_id) for agent_id in self._agents)
                if item.profile_id
            },
        }

    def validate_assets(self, assets) -> None:
        docs = _document_lookup(assets.knowledge_documents)
        known_agents = set(self._agents)
        known_agents.update(getattr(assets, "strategies", {}).keys())
        known_groups = set(RUNTIME_VISIBLE_GROUPS)
        known_groups.update(self._groups)
        known_groups.update(
            str(getattr(item, "group", "")).strip()
            for item in getattr(assets, "strategies", {}).values()
            if str(getattr(item, "group", "")).strip()
        )
        for agent_id in self._agents:
            spec = self.resolved_agent(agent_id)
            for name in spec.document_refs:
                _required_document(docs, name)
            for block in spec.prompt_blocks:
                if block.block_type == "workspace_document":
                    _required_document(docs, block.name)
            for group_id in spec.visible_groups:
                if group_id not in known_groups:
                    raise AgentFabricConfigError(f"{agent_id} references unknown visible group: {group_id}")
            for visible_agent in spec.visible_agents:
                if visible_agent not in known_agents:
                    raise AgentFabricConfigError(f"{agent_id} references unknown visible agent: {visible_agent}")

    def _block_payload(
        self,
        block: PromptBlockSpec,
        docs: Mapping[str, Any],
        shared_memory: Mapping[str, str],
        order: int,
    ) -> tuple[list[str], dict[str, Any]]:
        if block.block_type == "static_text":
            chunks = chunk_prompt_asset(block.title or "inline", block.text, "Static block", self._passage_char_limit)
            return chunks, _source_payload("static_text", block.title or "inline", order, chunks)
        if block.block_type == "prompt_file":
            text = (self._prompt_root / block.path).read_text(encoding="utf-8")
            chunks = chunk_prompt_asset(block.path, text, "Prompt file", self._passage_char_limit)
            return chunks, _source_payload("prompt_file", block.path, order, chunks)
        if block.block_type == "workspace_document":
            document = _required_document(docs, block.name)
            chunks = chunk_prompt_asset(document.name, document.content, "Workspace document", self._passage_char_limit)
            return chunks, _source_payload("workspace_document", document.name, order, chunks)
        if block.block_type == "workspace_file":
            relative_path, text = self._workspace_file_payload(block.path)
            chunks = chunk_prompt_asset(relative_path, text, "Workspace file", self._passage_char_limit)
            return chunks, _source_payload("workspace_file", relative_path, order, chunks)
        if block.block_type == "shared_memory":
            value = str(shared_memory.get(block.key, "")).strip()
            if not value:
                raise AgentFabricConfigError(f"shared_memory block is empty for key: {block.key}")
            chunks = chunk_prompt_asset(block.key, value, "Shared memory", self._passage_char_limit)
            return chunks, _source_payload("shared_memory", block.key, order, chunks)
        label, text = RUNTIME_BLOCKS[block.name]
        chunks = chunk_prompt_asset(block.name, text, label, self._passage_char_limit)
        return chunks, _source_payload("runtime_text", block.name, order, chunks)

    def _workspace_file_payload(self, relative_path: str) -> tuple[str, str]:
        path = _workspace_file_path(self._workspace_root, relative_path)
        return path.relative_to(self._workspace_root).as_posix(), _workspace_file_text(path)

    def _profile_ids(self) -> set[str]:
        if self.execution_registry is None:
            return set()
        catalog = self.execution_registry.export_catalog()
        return {str(item.get("profile_id", "")).strip() for item in catalog.get("profiles", [])}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AgentFabricConfigError(f"Missing agent fabric file: {path}")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _parse_phases(raw: Any) -> tuple[PhaseSpec, ...]:
    rows = []
    for item in _dict_list(raw, "phases"):
        rows.append(
            PhaseSpec(
                phase_id=_required_text(item, "phase_id"),
                active_groups=_tuple_text(item.get("active_groups")),
                default_profile_id=_optional_text(item.get("default_profile_id")),
                visible_groups=_tuple_text(item.get("visible_groups")),
                shared_memory_keys=_tuple_text(item.get("shared_memory_keys")),
                prompt_blocks=_parse_blocks(item.get("prompt_blocks")),
                limits=_mapping(item.get("limits")),
                metadata=_mapping(item.get("metadata")),
            )
        )
    return tuple(rows)


def _parse_groups(raw: Any) -> tuple[GroupSpec, ...]:
    rows = []
    for item in _dict_list(raw, "groups"):
        role_kind = _required_text(item, "role_kind")
        _validate_role_kind(role_kind, "group")
        rows.append(
            GroupSpec(
                group_id=_required_text(item, "group_id"),
                role_kind=role_kind,
                default_profile_id=_optional_text(item.get("default_profile_id")),
                visible_groups=_tuple_text(item.get("visible_groups")),
                shared_memory_keys=_tuple_text(item.get("shared_memory_keys")),
                prompt_blocks=_parse_blocks(item.get("prompt_blocks")),
                limits=_mapping(item.get("limits")),
                metadata=_mapping(item.get("metadata")),
            )
        )
    return tuple(rows)


def _load_agents(root: Path, groups: Mapping[str, GroupSpec], phases: Mapping[str, PhaseSpec], prompt_root: Path, profile_ids: set[str]) -> dict[str, AgentSpec]:
    if not root.is_dir():
        raise AgentFabricConfigError(f"Missing agent fabric directory: {root}")
    rows: dict[str, AgentSpec] = {}
    for path in sorted(root.glob("*.yaml")):
        raw = _read_yaml(path)
        spec = _parse_agent(raw, groups, phases, prompt_root, profile_ids)
        if spec.agent_id in rows:
            raise AgentFabricConfigError(f"Duplicate agent_id in agent fabric: {spec.agent_id}")
        rows[spec.agent_id] = spec
    return rows


def _parse_agent(raw: Mapping[str, Any], groups: Mapping[str, GroupSpec], phases: Mapping[str, PhaseSpec], prompt_root: Path, profile_ids: set[str]) -> AgentSpec:
    group_id = _required_text(raw, "group")
    if group_id not in groups:
        raise AgentFabricConfigError(f"Unknown group in agent fabric: {group_id}")
    role_kind = _required_text(raw, "role_kind")
    _validate_role_kind(role_kind, "agent")
    behavior = _required_text(raw, "behavior_template")
    expected = BEHAVIOR_ROLE_MAP.get(behavior)
    if expected != role_kind:
        raise AgentFabricConfigError(f"{_required_text(raw, 'agent_id')} uses incompatible behavior_template={behavior} for role_kind={role_kind}")
    agent_phases = _tuple_text(raw.get("phases"))
    if not agent_phases:
        raise AgentFabricConfigError(f"{_required_text(raw, 'agent_id')} must declare phases")
    for phase_id in agent_phases:
        if phase_id not in phases:
            raise AgentFabricConfigError(f"{_required_text(raw, 'agent_id')} references unknown phase: {phase_id}")
    profile_id = _optional_text(raw.get("profile_id"))
    if profile_id and profile_ids and profile_id not in profile_ids:
        raise AgentFabricConfigError(f"{_required_text(raw, 'agent_id')} references unknown profile_id: {profile_id}")
    prompt_root.mkdir(parents=True, exist_ok=True)
    return AgentSpec(
        agent_id=_required_text(raw, "agent_id"),
        display_name=_required_text(raw, "display_name"),
        description=_required_text(raw, "description"),
        behavior_template=behavior,
        role_kind=role_kind,
        group=group_id,
        phases=agent_phases,
        profile_id=profile_id,
        prompt_blocks=_parse_blocks(_mapping(raw.get("prompt")).get("blocks")),
        document_refs=_tuple_text(raw.get("document_refs")),
        shared_memory_keys=_tuple_text(raw.get("shared_memory_keys")),
        visible_groups=_tuple_text(raw.get("visible_groups")),
        visible_agents=_tuple_text(raw.get("visible_agents")),
        dialogue_policy=_parse_dialogue(_mapping(raw.get("dialogue_policy"))),
        limits=_mapping(raw.get("limits")),
        metadata=_mapping(raw.get("metadata")),
    )


def _parse_dialogue(raw: Mapping[str, Any]) -> DialoguePolicy:
    mode = _optional_text(raw.get("mode")) or "disabled"
    if mode not in SUPPORTED_DIALOGUE_MODES:
        raise AgentFabricConfigError(f"Unsupported dialogue_policy.mode: {mode}")
    rounds = int(raw.get("rounds", 0) or 0)
    return DialoguePolicy(mode=mode, rounds=rounds, metadata={key: value for key, value in raw.items() if key not in {"mode", "rounds"}})


def _parse_blocks(raw: Any) -> tuple[PromptBlockSpec, ...]:
    rows = []
    for item in _dict_list(raw, "prompt_blocks"):
        block_type = _required_text(item, "type")
        if block_type not in SUPPORTED_BLOCK_TYPES:
            raise AgentFabricConfigError(f"Unsupported prompt block type: {block_type}")
        path = _optional_text(item.get("path")) or ""
        name = _optional_text(item.get("name")) or ""
        key = _optional_text(item.get("key")) or ""
        text = _optional_text(item.get("text")) or ""
        if block_type == "static_text" and not text:
            raise AgentFabricConfigError("static_text prompt blocks require text")
        if block_type == "prompt_file" and not path:
            raise AgentFabricConfigError("prompt_file blocks require path")
        if block_type == "workspace_document" and not name:
            raise AgentFabricConfigError("workspace_document blocks require name")
        if block_type == "workspace_file" and not path:
            raise AgentFabricConfigError("workspace_file blocks require path")
        if block_type == "runtime_text" and name not in RUNTIME_BLOCKS:
            raise AgentFabricConfigError(f"Unknown runtime_text block: {name}")
        if block_type == "shared_memory" and not key:
            raise AgentFabricConfigError("shared_memory blocks require key")
        rows.append(
            PromptBlockSpec(
                block_type=block_type,
                title=_optional_text(item.get("title")) or "",
                text=text,
                path=path,
                name=name,
                key=key,
            )
        )
    return tuple(rows)


def _validate_role_kind(role_kind: str, label: str) -> None:
    if role_kind not in SUPPORTED_ROLE_KINDS:
        raise AgentFabricConfigError(f"Unsupported {label} role_kind: {role_kind}")


def _source_payload(source_type: str, name: str, order: int, chunks: Iterable[str]) -> dict[str, Any]:
    rows = list(chunks)
    return {"source_type": source_type, "name": name, "order": order, "chunk_count": len(rows), "chunks": rows}


def _document_lookup(documents) -> dict[str, Any]:
    return {str(getattr(item, "name", "")).strip().lower(): item for item in documents or () if str(getattr(item, "name", "")).strip()}


def _required_document(documents: Mapping[str, Any], name: str):
    try:
        return documents[name.lower()]
    except KeyError as exc:
        raise AgentFabricConfigError(f"Unknown workspace document reference: {name}") from exc


def _dict_list(raw: Any, label: str) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentFabricConfigError(f"{label} must be a list")
    return [item for item in raw if isinstance(item, Mapping)]


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    text = _optional_text(mapping.get(key))
    if text:
        return text
    raise AgentFabricConfigError(f"Missing required field: {key}")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tuple_text(*values: Any) -> tuple[str, ...]:
    rows: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            for item in value:
                text = _optional_text(item)
                if text and text not in rows:
                    rows.append(text)
    return tuple(rows)


def _dedupe_text(*values: Any) -> tuple[str, ...]:
    return _tuple_text(*values)


def _merge_prompt_blocks(*values: tuple[PromptBlockSpec, ...]) -> tuple[PromptBlockSpec, ...]:
    rows: list[PromptBlockSpec] = []
    for items in values:
        rows.extend(list(items or ()))
    return tuple(rows)


def _merge_mapping(*values: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        merged.update(dict(value or {}))
    return merged


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _first_profile_id(phases: list[PhaseSpec]) -> str | None:
    for item in phases:
        if item.default_profile_id:
            return item.default_profile_id
    return None


def _validate_block_files(prompt_root: Path, workspace_root: Path, block_sets: Iterable[tuple[PromptBlockSpec, ...]]) -> None:
    for blocks in block_sets:
        for block in blocks:
            if block.block_type == "prompt_file":
                path = (prompt_root / block.path).resolve()
                if not path.is_file():
                    raise AgentFabricConfigError(f"Unknown prompt file: {block.path}")
                continue
            if block.block_type == "workspace_file":
                _workspace_file_path(workspace_root, block.path)


def _workspace_file_path(workspace_root: Path, relative_path: str) -> Path:
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    if not normalized:
        raise AgentFabricConfigError("workspace_file blocks require path")
    path = (workspace_root / normalized).resolve()
    try:
        path.relative_to(workspace_root)
    except ValueError as exc:
        raise AgentFabricConfigError(f"workspace_file path escapes workspace root: {relative_path}") from exc
    if not path.is_file():
        raise AgentFabricConfigError(f"Unknown workspace file: {relative_path}")
    return path


def _workspace_file_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() != ".json":
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentFabricConfigError(f"Invalid JSON workspace file: {path}") from exc
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
