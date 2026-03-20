"""Runtime backend selection helpers for explicit no-MCP execution."""

from __future__ import annotations

import os

from ...config import reload_project_env


NO_MCP_BACKEND_AUTO = "auto"
NO_MCP_BACKEND_LOCAL = "local"
NO_MCP_BACKEND_LETTA = "letta"
VALID_NO_MCP_BACKENDS = {
    NO_MCP_BACKEND_AUTO,
    NO_MCP_BACKEND_LOCAL,
    NO_MCP_BACKEND_LETTA,
}


def world_v2_no_mcp_backend() -> str:
    reload_project_env()
    value = str(os.environ.get("LOTTERY_WORLD_NO_MCP_BACKEND", NO_MCP_BACKEND_AUTO)).strip().lower()
    if value in VALID_NO_MCP_BACKENDS:
        return value
    raise ValueError(f"Unsupported LOTTERY_WORLD_NO_MCP_BACKEND: {value}")
