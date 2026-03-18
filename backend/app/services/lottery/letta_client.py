"""Thin Letta API client used by the lottery world runtime."""

from __future__ import annotations

import os
from typing import Any

import requests
from requests import RequestException

from ...config import Config, PROJECT_ROOT_ENV, reload_project_env
from .letta_runtime_manager import ensure_local_letta_runtime


DEFAULT_TIMEOUT_SECONDS = 120


class LettaClient:
    """Minimal HTTP client for the Letta agent API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        server_api_key: str | None = None,
        model_name: str | None = None,
        embedding_model: str | None = None,
        session: requests.Session | None = None,
    ):
        reload_project_env()
        self.base_url = (base_url or os.environ.get("LETTA_BASE_URL") or Config.LETTA_BASE_URL).rstrip("/")
        self.api_key = (
            server_api_key
            or api_key
            or os.environ.get("LETTA_SERVER_API_KEY")
            or Config.LETTA_SERVER_API_KEY
        )
        self.model_name = str(model_name or os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME).strip()
        self.embedding_model = _prefixed_handle(
            embedding_model or os.environ.get("LETTA_EMBEDDING_MODEL") or Config.LETTA_EMBEDDING_MODEL,
        )
        self._managed_session = session is None
        self.session = session or requests.Session()
        self._resolved_model_name: str | None = None
        if not self.base_url:
            raise ValueError("LETTA_BASE_URL is not configured")
        if self._managed_session:
            ensure_local_letta_runtime(self.base_url)

    def create_agent(
        self,
        name: str,
        description: str,
        memory_blocks: dict[str, str],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "name": name,
            "description": description,
            "model": self._resolve_model_name(),
            "embedding": self.embedding_model,
            "include_base_tools": True,
            "message_buffer_autoclear": True,
            "memory_blocks": [
                {"label": label, "value": value}
                for label, value in memory_blocks.items()
            ],
        }
        if metadata:
            payload["metadata"] = metadata
        body = self._request_object("POST", "/agents/", payload)
        agent_id = str(body.get("id", "")).strip()
        if not agent_id:
            raise ValueError(f"Letta create_agent returned no id: {body}")
        return agent_id

    def update_block(self, agent_id: str, block_label: str, value: str) -> None:
        self._request_object(
            "PATCH",
            f"/agents/{agent_id}/core-memory/blocks/{block_label}",
            {"value": value},
        )

    def add_passage(
        self,
        agent_id: str,
        text: str,
        tags: list[str] | None = None,
    ) -> None:
        body = self._request_json(
            "POST",
            f"/agents/{agent_id}/archival-memory",
            {"text": text, "metadata": {"tags": tags or []}},
        )
        if not isinstance(body, list):
            raise ValueError(f"Letta archival-memory returned unexpected payload: {body}")

    def search_archival(self, agent_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        body = self._request_json(
            "GET",
            f"/agents/{agent_id}/archival-memory?query={query}&limit={limit}",
        )
        return body if isinstance(body, list) else []

    def append_core_block(self, agent_id: str, block_label: str, text: str) -> None:
        self._request_object(
            "POST",
            f"/agents/{agent_id}/core-memory/blocks/{block_label}/append",
            {"text": text},
        )

    def list_tools_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        body = self._request_json("GET", f"/agents/{agent_id}/tools")
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)]
        if isinstance(body, dict):
            items = body.get("items", [])
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def attach_tool_to_agent(self, agent_id: str, tool_id: str) -> dict[str, Any]:
        return self._request_object("PATCH", f"/agents/{agent_id}/tools/attach/{tool_id}")

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        body = self._request_json("GET", "/tools/mcp/servers")
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)]
        if isinstance(body, dict):
            items = body.get("items", body.get("servers", []))
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def add_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        return self._request_object("PUT", "/tools/mcp/servers", config)

    def connect_mcp_server(self, config: dict[str, Any]) -> dict[str, Any]:
        return self._request_object("POST", "/tools/mcp/servers/connect", config)

    def resync_mcp_server_tools(
        self,
        server_name: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        suffix = f"?agent_id={agent_id}" if agent_id else ""
        return self._request_object("POST", f"/tools/mcp/servers/{server_name}/resync{suffix}")

    def list_mcp_tools_by_server(self, server_name: str) -> list[dict[str, Any]]:
        body = self._request_json("GET", f"/tools/mcp/servers/{server_name}/tools")
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)]
        if isinstance(body, dict):
            items = body.get("items", body.get("tools", []))
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def execute_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request_object(
            "POST",
            f"/tools/mcp/servers/{server_name}/tools/{tool_name}/execute",
            {"args": args or {}},
        )

    def send_message(self, agent_id: str, content: str) -> str:
        body = self._request_object(
            "POST",
            f"/agents/{agent_id}/messages",
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": content}],
                    }
                ],
                "include_return_message_types": ["assistant_message"],
            },
        )
        return _extract_text(body)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except RequestException as exc:
            raise RuntimeError(_connection_error(self.base_url)) from exc
        if not response.ok:
            raise RuntimeError(f"Letta request failed: HTTP {response.status_code} {_preview(response.text)}")
        return response.json()

    def _request_object(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = self._request_json(method, path, payload)
        if not isinstance(body, dict):
            raise ValueError(f"Letta returned non-object body: {body}")
        return body

    def _resolve_model_name(self) -> str:
        if self._resolved_model_name:
            return self._resolved_model_name
        candidates = _model_candidates(self.model_name)
        try:
            response = self.session.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except RequestException as exc:
            raise RuntimeError(_connection_error(self.base_url)) from exc
        if not response.ok:
            raise RuntimeError(f"Letta model lookup failed: HTTP {response.status_code} {_preview(response.text)}")
        body = response.json()
        items = body if isinstance(body, list) else body.get("items", [])
        if not isinstance(items, list):
            raise ValueError(f"Letta /models returned unexpected payload: {body}")
        for candidate in candidates:
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("handle", "")).strip() == candidate:
                    self._resolved_model_name = candidate
                    return candidate
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).strip() == self.model_name:
                self._resolved_model_name = str(item.get("handle", "")).strip()
                return self._resolved_model_name
        raise ValueError(f"Letta model handle not found for {self.model_name!r}")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MiroFish-LotteryWorld/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def _model_candidates(model: str) -> list[str]:
    value = str(model or "").strip()
    if not value:
        raise ValueError("LLM model name is required for Letta agents")
    if "/" in value:
        return [value]
    return [value, f"openai-proxy/{value}", f"openai/{value}"]


def _prefixed_handle(value: str) -> str:
    handle = str(value or "").strip()
    if not handle:
        raise ValueError("Letta handle is required")
    if "/" in handle:
        return handle
    return f"openai/{handle}"


def _extract_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("content"), str) and body["content"].strip():
        return body["content"].strip()
    message = body.get("message")
    if isinstance(message, dict):
        text = _message_text(message)
        if text:
            return text
    messages = body.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            text = _message_text(item)
            if text:
                return text
    raise ValueError(f"Unable to extract Letta message content: {body}")


def _message_text(message: dict[str, Any]) -> str:
    message_type = str(message.get("message_type", "")).strip()
    if message_type and message_type != "assistant_message":
        return ""
    if isinstance(message.get("role"), str) and message["role"] != "assistant":
        return ""
    if isinstance(message.get("text"), str) and message["text"].strip():
        return message["text"].strip()
    return _content_text(message.get("content"))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        rows = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                rows.append(item["text"])
            elif isinstance(item, str):
                rows.append(item)
        return "\n".join(part.strip() for part in rows if part and part.strip()).strip()
    return ""


def _preview(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= 400:
        return compact
    return compact[:400].rstrip() + "..."


def _connection_error(base_url: str) -> str:
    return (
        f"Letta connection failed for {base_url}. "
        f"Check LETTA_BASE_URL in {PROJECT_ROOT_ENV} and ensure the Letta server is running."
    )
