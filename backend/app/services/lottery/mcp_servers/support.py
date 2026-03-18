"""Shared runtime helpers for lottery MCP servers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..kuzu_graph import KuzuGraphService
from ..world_store import WorldSessionStore


def session_id() -> str:
    value = str(os.environ.get("LOTTERY_WORLD_SESSION_ID", "")).strip()
    if not value:
        raise ValueError("LOTTERY_WORLD_SESSION_ID is not configured for the MCP server")
    return value


def store_root() -> Path:
    value = str(os.environ.get("LOTTERY_WORLD_STATE_ROOT", "")).strip()
    if not value:
        raise ValueError("LOTTERY_WORLD_STATE_ROOT is not configured for the MCP server")
    return Path(value)


@lru_cache(maxsize=1)
def world_store() -> WorldSessionStore:
    return WorldSessionStore(str(store_root()))


def load_session() -> dict[str, Any]:
    return world_store().load_session(session_id())


def save_session(session: dict[str, Any]) -> None:
    world_store().save_session(_session_dataclass(session))


@lru_cache(maxsize=1)
def kuzu_service() -> KuzuGraphService:
    root = str(os.environ.get("KUZU_GRAPH_ROOT", "")).strip() or None
    return KuzuGraphService(db_root=root)


def current_issue(session: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = session or load_session()
    round_state = dict(payload.get("current_round", {}))
    latest = dict(payload.get("latest_prediction", {}))
    return {
        "period": str(
            round_state.get("target_period")
            or latest.get("period")
            or payload.get("current_period")
            or "-"
        ).strip(),
        "phase": str(payload.get("current_phase", "idle")).strip(),
        "status": str(payload.get("status", "idle")).strip(),
        "brief": str(payload.get("shared_memory", {}).get("current_issue", "")).strip(),
    }


def _session_dataclass(session: dict[str, Any]):
    from ..world_v2_runtime import _session_dataclass as runtime_session_dataclass

    return runtime_session_dataclass(session)
