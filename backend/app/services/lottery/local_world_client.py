"""Local LLM-backed world client used when MCP is explicitly disabled."""

from __future__ import annotations

import json
from typing import Any

from ...config import Config
from ...utils.llm_client import LLMClient


DEFAULT_MAX_JSON_TOKENS = 1600
DEFAULT_MAX_TEXT_TOKENS = 1200
PASSAGE_LIMIT = 2
PASSAGE_CHARS = 800


class LocalWorldClient:
    """Explicit no-MCP runtime client backed by the configured LLM provider."""

    local_no_mcp = True
    runtime_backend = "local_no_mcp"

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}

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
        client = self._client(session)
        if _expects_json(content):
            payload = client.chat_json(messages, temperature=0.2, max_tokens=DEFAULT_MAX_JSON_TOKENS)
            return json.dumps(payload, ensure_ascii=False)
        return client.chat(messages, temperature=0.3, max_tokens=DEFAULT_MAX_TEXT_TOKENS)

    def _client(self, session: dict[str, Any]) -> LLMClient:
        model_name = str(session.get("llm_model_name") or Config.LLM_MODEL_NAME).strip()
        return LLMClient(model=model_name or None)

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
