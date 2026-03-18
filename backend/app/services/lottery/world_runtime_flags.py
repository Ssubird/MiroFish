"""Explicit runtime flags for lottery world execution."""

from __future__ import annotations

import os

from ...config import reload_project_env


TRUE_VALUES = {"1", "true", "yes", "on"}


def allow_world_v2_without_mcp() -> bool:
    """Return whether world_v2_market may run without Letta/MCP."""

    reload_project_env()
    value = str(os.environ.get("LOTTERY_WORLD_ALLOW_NO_MCP", "")).strip().lower()
    return value in TRUE_VALUES
