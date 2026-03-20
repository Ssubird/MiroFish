"""Local LLM-backed world client used when MCP is explicitly disabled."""

from __future__ import annotations

import json
from typing import Any

from ...utils.llm_client import LLMClient
from .execution_models import ExecutionProfile, ResolvedExecutionBinding
from .execution_registry import ExecutionRegistry


DEFAULT_MAX_JSON_TOKENS = 1600
DEFAULT_MAX_TEXT_TOKENS = 1200
PASSAGE_LIMIT = 2
PASSAGE_CHARS = 800


class LocalWorldClient:
    """Explicit no-MCP runtime client backed by the configured LLM provider."""

    local_no_mcp = True
    runtime_backend = "local_no_mcp"

    def __init__(self, execution_registry: ExecutionRegistry | None = None) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._registry = execution_registry or ExecutionRegistry()

    def create_agent(
        self,
        name: str,
        description: str,
        memory_blocks: dict[str, str],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        agent_id = f"local_{name}"
        self._agents[agent_id] = {
            "name": name,
            "description": description,
            "memory_blocks": dict(memory_blocks),
            "metadata": dict(metadata or {}),
            "passages": [],
        }
        return agent_id

    def update_block(self, agent_id: str, block_label: str, value: str) -> None:
        self._agent(agent_id)["memory_blocks"][block_label] = value

    def add_passage(self, agent_id: str, text: str, tags: list[str] | None = None) -> None:
        del tags
        self._agent(agent_id)["passages"].append(str(text).strip())

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        return []

    def add_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def connect_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def resync_mcp_server_tools(
        self,
        server_name: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return {"server_name": server_name, "agent_id": agent_id}

    def list_mcp_tools_by_server(self, server_name: str) -> list[dict[str, Any]]:
        del server_name
        return []

    def list_tools_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        del agent_id
        return []

    def attach_tool_to_agent(self, agent_id: str, tool_id: str) -> dict[str, Any]:
        return {"agent_id": agent_id, "tool_id": tool_id}

    def send_message(self, agent_id: str, content: str) -> str:
        return self.send_message_for_session({}, agent_id, content)

    def send_message_for_session(self, session: dict[str, Any], agent_id: str, content: str) -> str:
        agent = self._agent(agent_id)
        messages = self._messages(agent, content)
        expect_json = _expects_json(content)
        errors = []
        for binding in self._bindings_for_agent(session, agent_id):
            try:
                client = self._client_for_binding(binding)
                temperature = binding.temperature if expect_json else max(binding.temperature, 0.3)
                max_tokens = binding.max_tokens if expect_json else min(binding.max_tokens, DEFAULT_MAX_TEXT_TOKENS)
                self._record_binding_use(session, binding)
                if expect_json:
                    payload = client.chat_json(messages, temperature=temperature, max_tokens=max_tokens)
                    return json.dumps(payload, ensure_ascii=False)
                return client.chat(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as exc:
                errors.append(f"{binding.profile_id}: {exc}")
        raise RuntimeError("; ".join(errors))

    def _client_for_binding(self, binding: ResolvedExecutionBinding) -> LLMClient:
        profile = self._registry.profile(binding.profile_id)
        return self._registry.build_client(profile)

    def _bindings_for_agent(self, session: dict[str, Any], agent_id: str) -> list[ResolvedExecutionBinding]:
        binding = self._binding_for_agent(session, agent_id)
        rows = [binding]
        for profile_id in binding.fallback_profile_ids:
            fallback = self._registry.resolve_binding(
                binding.agent_id,
                binding.role_kind,
                binding.group,
                {"agent_overrides": {binding.agent_id: profile_id}, "group_overrides": {}},
                routing_mode="active",
            )
            rows.append(
                ResolvedExecutionBinding(
                    **{
                        **fallback.to_dict(),
                        "fallback_profile_ids": (),
                        "metadata": {**dict(fallback.metadata), "fallback_from": binding.profile_id},
                    }
                )
            )
        return rows

    def _binding_for_agent(self, session: dict[str, Any], agent_id: str) -> ResolvedExecutionBinding:
        agent = self._agent(agent_id)
        session_agent_id = str((agent.get("metadata") or {}).get("session_agent_id") or agent_id).strip()
        resolved = dict(session.get("resolved_execution_bindings") or {})
        if session_agent_id in resolved:
            payload = dict(resolved[session_agent_id])
            return ResolvedExecutionBinding(
                agent_id=session_agent_id,
                role_kind=str(payload.get("role_kind", "generator")),
                group=payload.get("group"),
                profile_id=str(payload.get("profile_id", "default")),
                provider_id=str(payload.get("provider_id", "default")),
                model_id=str(payload.get("model_id", "default")),
                temperature=float(payload.get("temperature", 0.7)),
                max_tokens=int(payload.get("max_tokens", 2000)),
                json_mode=bool(payload.get("json_mode", False)),
                retry_count=int(payload.get("retry_count", 2)),
                retry_backoff_ms=int(payload.get("retry_backoff_ms", 1500)),
                timeout_s=int(payload.get("timeout_s", 120)),
                prompt_style=str(payload.get("prompt_style", "strict_json")),
                fallback_profile_ids=tuple(payload.get("fallback_profile_ids") or ()),
                routing_mode=str(payload.get("routing_mode", "active")),
                metadata=dict(payload.get("metadata") or {}),
            )
        return self._resolved_binding_from_metadata(agent_id)

    def _resolved_binding_from_metadata(self, agent_id: str) -> ResolvedExecutionBinding:
        profile = self._profile_from_metadata(agent_id)
        agent = self._agent(agent_id)
        role_kind = str((agent.get("metadata") or {}).get("role_kind", "generator"))
        group = (agent.get("metadata") or {}).get("group")
        return ResolvedExecutionBinding(
            agent_id=str((agent.get("metadata") or {}).get("session_agent_id") or agent_id),
            role_kind=role_kind,
            group=group,
            profile_id=profile.profile_id,
            provider_id=profile.provider_id,
            model_id=profile.model_id,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            json_mode=profile.json_mode,
            retry_count=profile.retry_count,
            retry_backoff_ms=profile.retry_backoff_ms,
            timeout_s=profile.timeout_s,
            prompt_style=profile.prompt_style,
            fallback_profile_ids=profile.fallback_profile_ids,
            routing_mode="active",
        )

    def _profile_from_metadata(self, agent_id: str) -> ExecutionProfile:
        agent = self._agent(agent_id)
        metadata = agent.get("metadata") or {}
        role_kind = metadata.get("role_kind", "generator")
        group = metadata.get("group")
        return self._registry.resolve_profile(agent_id, role_kind, group)

    def _record_binding_use(self, session: dict[str, Any], binding: ResolvedExecutionBinding) -> None:
        metrics = session.setdefault("request_metrics", {})
        metrics["last_profile_id"] = binding.profile_id
        metrics["last_provider_id"] = binding.provider_id
        metrics["last_model_id"] = binding.model_id
        metrics["binding_uses"] = int(metrics.get("binding_uses", 0)) + 1

    def _agent(self, agent_id: str) -> dict[str, Any]:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise ValueError(f"Unknown local world agent: {agent_id}") from exc

    def _messages(self, agent: dict[str, Any], content: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": _system_prompt(agent)},
            {"role": "user", "content": str(content).strip()},
        ]


def _expects_json(content: str) -> bool:
    compact = str(content)
    markers = ('Return JSON only', '返回 JSON', '"numbers"', '"comment"', '"plan_type"')
    return any(marker in compact for marker in markers)


def _system_prompt(agent: dict[str, Any]) -> str:
    blocks = agent.get("memory_blocks", {})
    block_lines = [f"- {key}: {value}" for key, value in blocks.items() if str(value).strip()]
    passages = [_clip(text) for text in list(agent.get("passages", []))[:PASSAGE_LIMIT]]
    sections = [
        "You are running inside MiroFish world_v2_market explicit no-MCP mode.",
        "There is no Letta orchestration and no MCP tool execution in this run.",
        f"Agent: {agent.get('name', '-')}",
        f"Description: {agent.get('description', '-')}",
        "Memory blocks:",
        *(block_lines or ["- none"]),
        "Prompt passages:",
        *(passages or ["- none"]),
        "When the user prompt asks for JSON, return JSON only.",
    ]
    return "\n".join(sections)


def _clip(text: str) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= PASSAGE_CHARS:
        return f"- {compact}"
    return f"- {compact[:PASSAGE_CHARS].rstrip()}..."
