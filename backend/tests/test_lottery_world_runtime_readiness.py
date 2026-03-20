from pathlib import Path
import tempfile
from unittest.mock import patch

from app import create_app
from app.services.lottery.constants import WORLD_V2_MARKET_RUNTIME_MODE
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.world_runtime_readiness import (
    WorldRuntimePreflightError,
    runtime_readiness,
)

from test_lottery_world_runtime import _service


def test_runtime_readiness_reports_missing_letta_base_url(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._letta_base_url",
        lambda: ("", "unset"),
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "letta_not_configured"


def test_runtime_readiness_reports_missing_local_prerequisites(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_runtime_details",
        lambda: {"ready": False, "details": ["Letta CLI not found: x"]},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_openapi",
        lambda base_url: {"reachable": False, "details": ["connection refused"], "status_code": None},
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "local_letta_prereq_missing"


def test_runtime_readiness_requires_same_machine_self_hosted_letta(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._letta_base_url",
        lambda: ("https://app.letta.com/v1", "env"),
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "self_hosted_letta_required"


def test_runtime_readiness_reports_unreachable_letta(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_runtime_details",
        lambda: {"ready": True, "details": []},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_openapi",
        lambda base_url: {"reachable": False, "details": ["timeout"], "status_code": None},
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "letta_unreachable"


def test_runtime_readiness_reports_stdio_unsupported(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_runtime_details",
        lambda: {"ready": True, "details": []},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_openapi",
        lambda base_url: {"reachable": True, "details": [], "status_code": 200},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_stdio_support",
        lambda base_url: {
            "supported": False,
            "blocking_code": "mcp_stdio_unsupported",
            "blocking_message": "stdio MCP unavailable",
            "details": ["HTTP 400 stdio is not supported"],
        },
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "mcp_stdio_unsupported"


def test_runtime_readiness_reports_ready_when_all_checks_pass(monkeypatch):
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness.allow_world_v2_without_mcp",
        lambda: False,
    )
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_runtime_details",
        lambda: {"ready": True, "details": []},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_openapi",
        lambda base_url: {"reachable": True, "details": [], "status_code": 200},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_stdio_support",
        lambda base_url: {"supported": True, "details": [], "status_code": 200},
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is True
    assert readiness["blocking_code"] is None


def test_runtime_readiness_allows_explicit_no_mcp_mode(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._explicit_letta_base_url",
        lambda: "",
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is True
    assert readiness["runtime_backend"] == "local_no_mcp"
    assert readiness["mcp"]["required"] is False


def test_runtime_readiness_prefers_letta_when_explicit_no_mcp_has_letta(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LOTTERY_WORLD_NO_MCP_BACKEND", "auto")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._explicit_letta_base_url",
        lambda: "http://127.0.0.1:8283/v1",
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_runtime_details",
        lambda: {"ready": True, "details": []},
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._probe_openapi",
        lambda base_url: {"reachable": True, "details": [], "status_code": 200},
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is True
    assert readiness["runtime_backend"] == "letta_no_mcp"
    assert readiness["mcp"]["required"] is False
    assert readiness["letta"]["configured"] is True


def test_runtime_readiness_can_force_local_backend_with_letta_configured(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LOTTERY_WORLD_NO_MCP_BACKEND", "local")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._explicit_letta_base_url",
        lambda: "http://127.0.0.1:8283/v1",
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is True
    assert readiness["runtime_backend"] == "local_no_mcp"
    assert readiness["letta"]["configured"] is False
    assert readiness["mcp"]["required"] is False


def test_runtime_readiness_blocks_local_no_mcp_without_llm(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._explicit_letta_base_url",
        lambda: "",
    )
    monkeypatch.setattr(
        "app.services.lottery.world_runtime_readiness._local_no_mcp_details",
        lambda: ["LLM_API_KEY is required for explicit no-MCP world runtime."],
    )

    readiness = runtime_readiness(WORLD_V2_MARKET_RUNTIME_MODE)

    assert readiness["ready"] is False
    assert readiness["blocking_code"] == "llm_not_configured_for_local_runtime"


def test_prepare_world_session_blocks_before_creating_session():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        with patch(
            "app.services.lottery.research_service.ensure_runtime_ready",
            side_effect=WorldRuntimePreflightError(
                {
                    "runtime_mode": WORLD_V2_MARKET_RUNTIME_MODE,
                    "ready": False,
                    "blocking_code": "mcp_stdio_unsupported",
                    "blocking_message": "stdio MCP unavailable",
                    "details": ["need self-hosted Letta"],
                }
            ),
        ):
            try:
                service.prepare_world_session(
                    pick_size=5,
                    strategy_ids=["cold_rule", "hot_rule"],
                    issue_parallelism=1,
                    runtime_mode=WORLD_V2_MARKET_RUNTIME_MODE,
                )
            except WorldRuntimePreflightError as exc:
                error = exc
            else:
                raise AssertionError("Expected WorldRuntimePreflightError")

        store = service.world_runtime.store

    assert error.readiness["blocking_code"] == "mcp_stdio_unsupported"
    assert store.current_session_id() is None


def test_world_api_returns_412_when_runtime_not_ready():
    app = create_app()
    client = app.test_client()
    readiness = {
        "runtime_mode": WORLD_V2_MARKET_RUNTIME_MODE,
        "ready": False,
        "blocking_code": "mcp_stdio_unsupported",
        "blocking_message": "stdio MCP unavailable",
        "details": ["need self-hosted Letta"],
    }

    with patch("app.api.lottery.service.ensure_world_runtime_ready", side_effect=WorldRuntimePreflightError(readiness)):
        with patch("app.api.lottery.world_runs.start") as start_run:
            response = client.post("/api/lottery/world/advance", json={"strategy_ids": ["cold_50"]})

    payload = response.get_json()
    assert response.status_code == 412
    assert payload["success"] is False
    assert payload["data"]["blocking_code"] == "mcp_stdio_unsupported"
    start_run.assert_not_called()


def test_runtime_readiness_api_returns_structured_payload():
    app = create_app()
    client = app.test_client()
    payload = {
        "runtime_mode": WORLD_V2_MARKET_RUNTIME_MODE,
        "ready": False,
        "blocking_code": "local_letta_prereq_missing",
        "blocking_message": "missing local prereqs",
        "details": ["Letta CLI not found"],
    }

    with patch.object(LotteryResearchService, "get_world_runtime_readiness", return_value=payload):
        response = client.get("/api/lottery/world/runtime-readiness")

    body = response.get_json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["blocking_code"] == "local_letta_prereq_missing"
