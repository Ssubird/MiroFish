import requests
from unittest.mock import patch

from app.services.lottery.letta_client import LettaClient


class FakeResponse:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok
        self.status_code = 200 if ok else 500
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.requests = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append(("GET", url, None))
        return FakeResponse([{"handle": "openai/gpt-5.4", "name": "gpt-5.4"}])

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.requests.append((method, url, json))
        if url.endswith("/agents/"):
            return FakeResponse({"id": "agent-1"})
        if url.endswith("/agents/agent-1/tools") and method == "GET":
            return FakeResponse([{"id": "tool-1"}, {"id": "tool-2"}])
        if url.endswith("/agents/agent-1/tools/attach/tool-9") and method == "PATCH":
            return FakeResponse({"ok": True})
        if url.endswith("/tools/mcp/servers") and method == "GET":
            return FakeResponse([{"server_name": "happy8_rules_mcp"}])
        if url.endswith("/tools/mcp/servers") and method == "PUT":
            return FakeResponse({"server_name": json["server_name"]})
        if url.endswith("/tools/mcp/servers/connect") and method == "POST":
            return FakeResponse({"server_name": json["server_name"], "connected": True})
        if url.endswith("/tools/mcp/servers/happy8_rules_mcp/resync") and method == "POST":
            return FakeResponse({"server_name": "happy8_rules_mcp", "resynced": True})
        if url.endswith("/tools/mcp/servers/happy8_rules_mcp/tools") and method == "GET":
            return FakeResponse([{"id": "tool-9", "name": "validate_plan"}])
        if url.endswith("/tools/mcp/servers/happy8_rules_mcp/tools/validate_plan/execute") and method == "POST":
            return FakeResponse({"ok": True, "args": json["args"]})
        if url.endswith("/messages"):
            return FakeResponse(
                {
                    "messages": [
                        {
                            "message_type": "event_message",
                            "event_type": "compaction",
                            "event_data": {"hidden": 4},
                        },
                        {
                            "message_type": "assistant_message",
                            "content": [{"type": "text", "text": '{"plan_type":"tickets"}'}],
                        },
                    ],
                    "stop_reason": {"message_type": "stop_reason", "stop_reason": "end_turn"},
                    "usage": {},
                }
            )
        raise AssertionError(f"Unexpected request: {method} {url}")


class BrokenSession:
    def get(self, url, headers=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    def request(self, method, url, headers=None, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")


def test_create_agent_enables_message_buffer_autoclear():
    session = FakeSession()
    client = LettaClient(
        base_url="http://127.0.0.1:8283/v1",
        model_name="gpt-5.4",
        embedding_model="openai/text-embedding-3-large",
        session=session,
    )

    client.create_agent("budget_guard", "guard", {"persona": "guard"})

    payload = session.requests[-1][2]
    assert payload["message_buffer_autoclear"] is True


def test_send_message_ignores_system_events_and_returns_assistant_text():
    session = FakeSession()
    client = LettaClient(
        base_url="http://127.0.0.1:8283/v1",
        model_name="gpt-5.4",
        embedding_model="openai/text-embedding-3-large",
        session=session,
    )

    text = client.send_message("agent-1", "Return JSON only")

    payload = session.requests[-1][2]
    assert payload["include_return_message_types"] == ["assistant_message"]
    assert text == '{"plan_type":"tickets"}'


def test_create_agent_surfaces_clear_connection_error():
    client = LettaClient(
        base_url="http://127.0.0.1:8283/v1",
        model_name="gpt-5.4",
        embedding_model="openai/text-embedding-3-large",
        session=BrokenSession(),
    )

    try:
        client.create_agent("budget_guard", "guard", {"persona": "guard"})
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected RuntimeError")

    assert "LETTA_BASE_URL" in message
    assert "127.0.0.1:8283" in message


def test_client_bootstraps_local_runtime_for_managed_session():
    with patch("app.services.lottery.letta_client.ensure_local_letta_runtime") as ensure:
        LettaClient(
            base_url="http://127.0.0.1:8283/v1",
            model_name="gpt-5.4",
            embedding_model="openai/text-embedding-3-large",
        )

    ensure.assert_called_once_with("http://127.0.0.1:8283/v1")


def test_client_supports_agent_tool_attachment_and_mcp_endpoints():
    session = FakeSession()
    client = LettaClient(
        base_url="http://127.0.0.1:8283/v1",
        model_name="gpt-5.4",
        embedding_model="openai/text-embedding-3-large",
        session=session,
    )

    tools = client.list_tools_for_agent("agent-1")
    attach = client.attach_tool_to_agent("agent-1", "tool-9")
    servers = client.list_mcp_servers()
    added = client.add_mcp_server({"server_name": "happy8_rules_mcp"})
    connected = client.connect_mcp_server({"server_name": "happy8_rules_mcp"})
    resynced = client.resync_mcp_server_tools("happy8_rules_mcp")
    server_tools = client.list_mcp_tools_by_server("happy8_rules_mcp")
    executed = client.execute_mcp_tool("happy8_rules_mcp", "validate_plan", {"plan": "{}"})

    assert [item["id"] for item in tools] == ["tool-1", "tool-2"]
    assert attach["ok"] is True
    assert servers[0]["server_name"] == "happy8_rules_mcp"
    assert added["server_name"] == "happy8_rules_mcp"
    assert connected["connected"] is True
    assert resynced["resynced"] is True
    assert server_tools[0]["name"] == "validate_plan"
    assert executed["args"] == {"plan": "{}"}
