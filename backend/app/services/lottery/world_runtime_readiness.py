"""Readiness checks for lottery persistent world runtimes."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import Any
from urllib.parse import urlparse

import requests
from requests import RequestException

from ...config import Config, PROJECT_ROOT, reload_project_env
from .constants import WORLD_V2_MARKET_RUNTIME_MODE
from .letta_runtime_support import RuntimePaths, runtime_paths
from .world_runtime_backend import (
    NO_MCP_BACKEND_LETTA,
    NO_MCP_BACKEND_LOCAL,
    world_v2_no_mcp_backend,
)
from .world_runtime_flags import allow_world_v2_without_mcp


HTTP_TIMEOUT_SECONDS = 5
STDIO_UNSUPPORTED_TEXT = "stdio is not supported in the current environment"
STDIO_DISABLED_TEXT = "MCP stdio servers are disabled"
STDIO_PROBE_SERVER = "mirofish_runtime_probe"


class WorldRuntimePreflightError(RuntimeError):
    """Raised when a runtime is requested before its dependencies are ready."""

    def __init__(self, readiness: dict[str, Any]):
        self.readiness = readiness
        message = str(readiness.get("blocking_message") or "World runtime is not ready")
        super().__init__(message)


def runtime_readiness(runtime_mode: str, letta_client: object | None = None) -> dict[str, Any]:
    mode = str(runtime_mode or "").strip() or WORLD_V2_MARKET_RUNTIME_MODE
    if mode != WORLD_V2_MARKET_RUNTIME_MODE:
        return _ready_payload(mode)
    if allow_world_v2_without_mcp():
        backend = world_v2_no_mcp_backend()
        env_letta_base_url = _explicit_letta_base_url()
        if backend == NO_MCP_BACKEND_LOCAL:
            return _local_no_mcp_payload(mode)
        if backend == NO_MCP_BACKEND_LETTA:
            if env_letta_base_url:
                return _letta_no_mcp_payload(mode, env_letta_base_url.rstrip("/"), "env")
            return _blocked(
                _base_payload(mode, "", "unset"),
                "letta_not_configured",
                "LOTTERY_WORLD_NO_MCP_BACKEND=letta but LETTA_BASE_URL is not configured.",
                ["Set LETTA_BASE_URL or switch LOTTERY_WORLD_NO_MCP_BACKEND to local/auto."],
            )
        if env_letta_base_url:
            return _letta_no_mcp_payload(mode, env_letta_base_url.rstrip("/"), "env")
        return _local_no_mcp_payload(mode)
    if _uses_injected_client(letta_client):
        return _injected_client_payload(mode, letta_client)
    return _world_v2_market_readiness(mode)


def ensure_runtime_ready(runtime_mode: str, letta_client: object | None = None) -> None:
    readiness = runtime_readiness(runtime_mode, letta_client)
    if not readiness.get("ready"):
        raise WorldRuntimePreflightError(readiness)


def _world_v2_market_readiness(runtime_mode: str) -> dict[str, Any]:
    reload_project_env()
    base_url, source = _letta_base_url()
    payload = _base_payload(runtime_mode, base_url, source)
    if not base_url:
        return _blocked(
            payload,
            "letta_not_configured",
            "未配置 LETTA_BASE_URL，`world_v2_market` 无法检查 Letta / MCP 运行前置条件。",
            ["请先在项目 `.env` 中设置可用的 `LETTA_BASE_URL`。"],
        )
    if not payload["local_runtime"]["same_machine"]:
        return _blocked(
            payload,
            "self_hosted_letta_required",
            "当前 `world_v2_market` 依赖同机自托管 Letta 执行本地 stdio MCP server，远程/托管 Letta 目前不在支持范围内。",
            [f"LETTA_BASE_URL={base_url}"],
        )
    prereq_details = _local_runtime_details()
    payload["local_runtime"].update(prereq_details)
    letta_probe = _probe_openapi(base_url)
    payload["letta"].update(letta_probe)
    if not letta_probe["reachable"] and not prereq_details["ready"]:
        return _blocked(
            payload,
            "local_letta_prereq_missing",
            "本地 Letta 自托管前置条件未就绪，当前无法启动 `world_v2_market`。",
            prereq_details["details"],
        )
    if not letta_probe["reachable"]:
        return _blocked(
            payload,
            "letta_unreachable",
            "无法连接到当前 LETTA_BASE_URL，`world_v2_market` 不能开始运行。",
            [f"LETTA_BASE_URL={base_url}", *letta_probe["details"]],
        )
    mcp_probe = _probe_stdio_support(base_url)
    payload["mcp"].update(mcp_probe)
    if mcp_probe["supported"]:
        payload["ready"] = True
        return payload
    code = str(mcp_probe.get("blocking_code") or "mcp_stdio_unsupported")
    message = str(mcp_probe.get("blocking_message") or "当前 Letta 环境不支持 stdio MCP。")
    details = list(mcp_probe.get("details") or [])
    return _blocked(payload, code, message, details)


def _base_payload(runtime_mode: str, base_url: str, source: str) -> dict[str, Any]:
    return {
        "runtime_mode": runtime_mode,
        "ready": False,
        "blocking_code": None,
        "blocking_message": None,
        "details": [],
        "letta": {
            "configured": bool(base_url),
            "base_url": base_url,
            "source": source,
            "reachable": False,
            "details": [],
        },
        "mcp": {
            "required": True,
            "transport": "stdio",
            "supported": False,
            "probe_server": STDIO_PROBE_SERVER,
            "details": [],
        },
        "local_runtime": {
            "same_machine": _is_same_machine_base_url(base_url),
            "ready": False,
            "details": [],
        },
    }


def _ready_payload(runtime_mode: str) -> dict[str, Any]:
    return {
        "runtime_mode": runtime_mode,
        "ready": True,
        "blocking_code": None,
        "blocking_message": None,
        "summary": "Current world runtime is ready.",
        "runtime_backend": "default",
        "details": [],
        "letta": {"configured": False, "base_url": "", "source": "unused", "reachable": False, "details": []},
        "mcp": {"required": False, "transport": None, "supported": False, "probe_server": None, "details": []},
        "local_runtime": {"same_machine": False, "ready": False, "details": []},
    }


def _injected_client_payload(runtime_mode: str, letta_client: object) -> dict[str, Any]:
    mcp_disabled = bool(getattr(letta_client, "mcp_disabled", False))
    runtime_backend = str(getattr(letta_client, "runtime_backend", "default")).strip() or "default"
    return {
        "runtime_mode": runtime_mode,
        "ready": True,
        "blocking_code": None,
        "blocking_message": None,
        "summary": "Injected runtime client is ready.",
        "runtime_backend": runtime_backend,
        "details": ["检测到注入式 Letta client，跳过外部 readiness HTTP 探测。"],
        "letta": {
            "configured": True,
            "base_url": "",
            "source": type(letta_client).__name__,
            "reachable": True,
            "details": [],
        },
        "mcp": {
            "required": not mcp_disabled,
            "transport": None if mcp_disabled else "stdio",
            "supported": False if mcp_disabled else True,
            "probe_server": None,
            "details": [
                "由注入式 client 接管 agent 行为。",
                "MCP tooling is disabled explicitly for this client." if mcp_disabled else "由注入式 client 接管 MCP/agent 行为。",
            ],
        },
        "local_runtime": {"same_machine": True, "ready": True, "details": []},
    }


def _letta_no_mcp_payload(runtime_mode: str, base_url: str, source: str) -> dict[str, Any]:
    payload = _base_payload(runtime_mode, base_url, source)
    payload["summary"] = "Explicit no-MCP mode will keep Letta agent and memory orchestration enabled."
    payload["runtime_backend"] = "letta_no_mcp"
    payload["mcp"] = {
        "required": False,
        "transport": None,
        "supported": False,
        "probe_server": None,
        "details": ["MCP registration is disabled explicitly; Letta agent and memory APIs remain enabled."],
    }
    if not payload["local_runtime"]["same_machine"]:
        letta_probe = _probe_openapi(base_url)
        payload["letta"].update(letta_probe)
        if letta_probe["reachable"]:
            payload["ready"] = True
            payload["details"] = ["Using Letta without MCP tooling.", f"LETTA_BASE_URL={base_url}"]
            return payload
        return _blocked(
            payload,
            "letta_unreachable",
            "无法连接到当前 LETTA_BASE_URL，显式无 MCP 的 Letta 运行模式不能开始。",
            [f"LETTA_BASE_URL={base_url}", *letta_probe["details"]],
        )
    prereq_details = _local_runtime_details()
    payload["local_runtime"].update(prereq_details)
    letta_probe = _probe_openapi(base_url)
    payload["letta"].update(letta_probe)
    if letta_probe["reachable"] or prereq_details["ready"]:
        payload["ready"] = True
        payload["details"] = [
            "Using Letta agent and memory orchestration without MCP tooling.",
            f"LETTA_BASE_URL={base_url}",
        ]
        if not letta_probe["reachable"]:
            payload["details"].append("Local Letta runtime is not up yet, but the required bootstrap prerequisites are ready.")
        return payload
    return _blocked(
        payload,
        "local_letta_prereq_missing",
        "显式无 MCP 模式想使用 Letta，但本地 Letta 运行前置条件未就绪。",
        prereq_details["details"],
    )


def _local_no_mcp_payload(runtime_mode: str) -> dict[str, Any]:
    details = _local_no_mcp_details()
    if details:
        return {
            "runtime_mode": runtime_mode,
            "ready": False,
            "blocking_code": "llm_not_configured_for_local_runtime",
            "blocking_message": "已启用显式无 MCP 模式，但本地 LLM 运行前置条件未满足。",
            "summary": "显式无 MCP 模式已开启，但当前还缺少本地 LLM 运行条件。",
            "runtime_backend": "local_no_mcp",
            "details": details,
            "letta": {"configured": False, "base_url": "", "source": "disabled", "reachable": False, "details": []},
            "mcp": {
                "required": False,
                "transport": None,
                "supported": False,
                "probe_server": None,
                "details": ["已显式关闭 MCP，world_v2_market 将不注册 Letta/MCP 工具。"],
            },
            "local_runtime": {"same_machine": True, "ready": False, "details": details},
        }
    return {
        "runtime_mode": runtime_mode,
        "ready": True,
        "blocking_code": None,
        "blocking_message": None,
        "summary": "已启用显式无 MCP 模式，world_v2_market 将使用本地 LLM orchestration 启动。",
        "runtime_backend": "local_no_mcp",
        "details": [
            "LOTTERY_WORLD_ALLOW_NO_MCP=true",
            "本次运行不会使用 Letta agent / memory / MCP orchestration。",
            "world_v2_market 将直接使用本地 LLM 调度 social、judge、bettor 和 purchase_chair。",
        ],
        "letta": {
            "configured": False,
            "base_url": "",
            "source": "disabled_by_flag",
            "reachable": False,
            "details": ["显式无 MCP 模式已跳过 Letta readiness 检查。"],
        },
        "mcp": {
            "required": False,
            "transport": None,
            "supported": False,
            "probe_server": None,
            "details": ["显式无 MCP 模式已关闭 MCP 注册与工具编排。"],
        },
        "local_runtime": {"same_machine": True, "ready": True, "details": []},
    }


def _blocked(
    payload: dict[str, Any],
    code: str,
    message: str,
    details: list[str],
) -> dict[str, Any]:
    payload["ready"] = False
    payload["blocking_code"] = code
    payload["blocking_message"] = message
    payload["details"] = details
    return payload


def _letta_base_url() -> tuple[str, str]:
    env_value = str(os.environ.get("LETTA_BASE_URL", "")).strip()
    if env_value:
        return env_value.rstrip("/"), "env"
    config_value = str(Config.LETTA_BASE_URL or "").strip()
    if config_value:
        return config_value.rstrip("/"), "config"
    return "", "unset"


def _explicit_letta_base_url() -> str:
    return str(os.environ.get("LETTA_BASE_URL", "")).strip()


def _uses_injected_client(letta_client: object | None) -> bool:
    return letta_client is not None and not hasattr(letta_client, "base_url")


def _is_same_machine_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if not host:
        return False
    return bool(_resolve_host(host) & _local_addresses())


def _resolve_host(host: str) -> set[str]:
    try:
        _, _, addresses = socket.gethostbyname_ex(host)
    except OSError:
        return set()
    return {item.strip() for item in addresses if item.strip()}


def _local_addresses() -> set[str]:
    addresses = {"127.0.0.1", "::1"}
    try:
        _, _, values = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        return addresses
    addresses.update(item.strip() for item in values if item.strip())
    return addresses


def _local_runtime_details() -> dict[str, Any]:
    details = _runtime_path_details()
    details.extend(_provider_details())
    return {"ready": not details, "details": details}


def _runtime_path_details() -> list[str]:
    try:
        paths = runtime_paths()
    except RuntimeError as exc:
        return [str(exc)]
    return _missing_runtime_paths(paths)


def _missing_runtime_paths(paths: RuntimePaths) -> list[str]:
    required = {
        "Letta CLI": paths.letta_cli,
        "Alembic CLI": paths.alembic_cli,
        "Letta migrations": paths.alembic_ini,
        "PostgreSQL pg_ctl.exe": paths.pg_bin / "pg_ctl.exe",
        "PostgreSQL initdb.exe": paths.pg_bin / "initdb.exe",
        "PostgreSQL psql.exe": paths.pg_bin / "psql.exe",
        "PostgreSQL createdb.exe": paths.pg_bin / "createdb.exe",
    }
    missing = []
    for label, path in required.items():
        if not path.exists():
            missing.append(f"{label} not found: {path}")
    return missing


def _provider_details() -> list[str]:
    checks = {
        "LLM_API_KEY": bool(str(os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY or "").strip()),
        "LLM_BASE_URL": bool(str(os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL or "").strip()),
        "LETTA_API_KEY": bool(str(os.environ.get("LETTA_API_KEY") or Config.LETTA_API_KEY or "").strip()),
    }
    return [f"{name} is required for project-local Letta provider bootstrap." for name, ok in checks.items() if not ok]


def _local_no_mcp_details() -> list[str]:
    checks = {
        "LLM_API_KEY": bool(str(os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY or "").strip()),
        "LLM_BASE_URL": bool(str(os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL or "").strip()),
    }
    return [f"{name} is required for explicit no-MCP world runtime." for name, ok in checks.items() if not ok]


def _probe_openapi(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rsplit('/v1', 1)[0]}/openapi.json" if base_url.endswith("/v1") else f"{base_url}/openapi.json"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    except RequestException as exc:
        return {"reachable": False, "status_code": None, "details": [str(exc)]}
    if response.ok:
        return {"reachable": True, "status_code": response.status_code, "details": []}
    return {
        "reachable": False,
        "status_code": response.status_code,
        "details": [f"HTTP {response.status_code} {_detail_text(response)}"],
    }


def _probe_stdio_support(base_url: str) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{base_url}/tools/mcp/servers/test",
            json=_probe_config(),
            headers=_letta_headers(),
            timeout=HTTP_TIMEOUT_SECONDS * 2,
        )
    except RequestException as exc:
        return {
            "supported": False,
            "blocking_code": "mcp_probe_failed",
            "blocking_message": "无法完成 Letta stdio MCP 探测。",
            "details": [str(exc)],
        }
    if response.ok:
        return {"supported": True, "status_code": response.status_code, "details": []}
    detail = _detail_text(response)
    if STDIO_UNSUPPORTED_TEXT in detail or STDIO_DISABLED_TEXT in detail:
        return {
            "supported": False,
            "blocking_code": "mcp_stdio_unsupported",
            "blocking_message": "当前 Letta 环境不支持 stdio MCP，`world_v2_market` 不能启动。",
            "details": [f"HTTP {response.status_code} {detail}"],
        }
    return {
        "supported": False,
        "blocking_code": "mcp_probe_failed",
        "blocking_message": "Letta 已可连接，但 stdio MCP 探测没有通过。",
        "details": [f"HTTP {response.status_code} {detail}"],
    }


def _probe_config() -> dict[str, Any]:
    backend_root = Path(PROJECT_ROOT).resolve() / "backend"
    pythonpath = [str(backend_root)]
    existing = str(os.environ.get("PYTHONPATH", "")).strip()
    if existing:
        pythonpath.append(existing)
    return {
        "server_name": STDIO_PROBE_SERVER,
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "app.services.lottery.mcp_servers.happy8_rules_mcp"],
        "env": {
            "PYTHONPATH": os.pathsep.join(pythonpath),
            "LOTTERY_DATA_ROOT": str(Path(PROJECT_ROOT).resolve() / "ziweidoushu"),
        },
    }


def _letta_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = str(os.environ.get("LETTA_SERVER_API_KEY") or Config.LETTA_SERVER_API_KEY or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _detail_text(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return " ".join((response.text or "").split())
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if isinstance(detail, str):
            return detail
    return " ".join(str(payload).split())
