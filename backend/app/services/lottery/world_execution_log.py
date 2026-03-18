"""Structured execution logs and failure summaries for lottery world runs."""

from __future__ import annotations

import os
from traceback import TracebackException
from typing import Any

from ...config import Config
from .world_models import world_id, world_now


MAX_EXECUTION_LOG_ENTRIES = 200
MAX_TRACEBACK_LINES = 10
STDIO_UNSUPPORTED_TEXT = "stdio is not supported in the current environment"
ARCHIVAL_MEMORY_LIMIT_TEXT = "Archival memory content exceeds token limit"
PURCHASE_PLAN_INVALID_TEXT = "purchase_chair returned invalid purchase plan:"
STATE_FILE_LOCK_TEXT = "session.json.tmp"


def append_execution_log(
    session: dict[str, Any],
    level: str,
    code: str,
    message: str,
    *,
    phase: str | None = None,
    details: Any = None,
) -> dict[str, Any]:
    entry = {
        "log_id": world_id("log"),
        "created_at": world_now(),
        "level": str(level or "info").strip() or "info",
        "phase": str(phase or session.get("current_phase") or "idle").strip() or "idle",
        "code": str(code or "world_log").strip() or "world_log",
        "message": str(message or "").strip() or str(code or "world_log"),
        "details": _normalize_details(details),
    }
    logs = list(session.get("execution_log") or [])
    logs.append(entry)
    session["execution_log"] = logs[-MAX_EXECUTION_LOG_ENTRIES:]
    return entry


def build_error_payload(
    exc: Exception,
    *,
    phase: str,
    period: str | None,
) -> dict[str, Any]:
    raw = str(exc).strip() or exc.__class__.__name__
    if ARCHIVAL_MEMORY_LIMIT_TEXT in raw:
        return {
            "code": "letta_archival_passage_too_large",
            "message": (
                "Letta archival memory 单条内容超过限制。通常是绑定的 prompt 文档过长，"
                "在注册 agent 时被作为单段 passage 写入。"
            ),
            "phase": phase,
            "period": period,
            "details": [
                f"LETTA_BASE_URL={_letta_base_url()}",
                "排查入口: market_role_registry.py -> agent_prompt_passages(...)",
                "查看 session.agent_state[*].bound_prompt_docs 与 bound_prompt_passage_count。",
                f"原始错误: {raw}",
            ],
        }
    if STDIO_UNSUPPORTED_TEXT in raw:
        return {
            "code": "mcp_stdio_unsupported",
            "message": (
                "当前 Letta 环境不支持 stdio MCP，`world_v2_market` 无法完成工具注册。"
            ),
            "phase": phase,
            "period": period,
            "details": [
                f"LETTA_BASE_URL={_letta_base_url()}",
                "当前运行链会通过 Letta 注册 stdio MCP server。",
                "你现在连接的 Letta 环境不支持这项能力。",
                f"原始错误: {raw}",
            ],
        }
    if PURCHASE_PLAN_INVALID_TEXT in raw:
        return {
            "code": "purchase_plan_invalid",
            "message": "purchase_chair returned a plan that failed executable budget/structure validation.",
            "phase": phase,
            "period": period,
            "details": [
                "Check execution_log entries with code=purchase_plan_invalid_attempt.",
                "All portfolio_legs are treated as live executable legs.",
                "Alternative or illustrative legs must stay in comment/rationale, not portfolio_legs.",
                f"Original error: {raw}",
            ],
        }
    if STATE_FILE_LOCK_TEXT in raw and ("WinError 5" in raw or "PermissionError" in raw):
        return {
            "code": "world_state_write_locked",
            "message": "world session state file was temporarily locked during save on Windows.",
            "phase": phase,
            "period": period,
            "details": [
                "Typical cause: frontend/API polling reads session.json while the background world thread is replacing it.",
                "Check backend/app/services/lottery/world_store.py for save retry behavior.",
                f"Original error: {raw}",
            ],
        }
    return {
        "code": "world_runtime_failed",
        "message": raw,
        "phase": phase,
        "period": period,
        "details": traceback_preview(exc),
    }


def traceback_preview(exc: Exception) -> list[str]:
    lines = [
        line.rstrip()
        for line in TracebackException.from_exception(exc).format()
        if line.strip()
    ]
    return lines[-MAX_TRACEBACK_LINES:]


def _normalize_details(details: Any) -> list[str]:
    if details is None:
        return []
    if isinstance(details, str):
        text = details.strip()
        return [text] if text else []
    if isinstance(details, (list, tuple)):
        rows = []
        for item in details:
            text = str(item).strip()
            if text:
                rows.append(text)
        return rows
    text = str(details).strip()
    return [text] if text else []


def _letta_base_url() -> str:
    return (
        str(os.environ.get("LETTA_BASE_URL") or "").strip()
        or str(Config.LETTA_BASE_URL).strip()
        or "-"
    )
