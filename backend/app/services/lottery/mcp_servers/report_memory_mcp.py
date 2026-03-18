"""Report memory MCP server backed by world report artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .support import current_issue, kuzu_service, load_session, save_session


mcp = FastMCP("ReportMemoryMCP")


@mcp.tool()
def report_digest(period: str) -> str:
    """Get the latest report digest for the current world."""
    session = load_session()
    if period and current_issue(session)["period"] != period:
        return f"No active digest loaded for {period}."
    shared = session.get("shared_memory", {})
    digest = str(shared.get("report_digest", "")).strip()
    if digest:
        return digest
    return _report_text(session)[:1200] or "No report artifacts available."


@mcp.tool()
def find_report_evidence(claim: str) -> str:
    """Search the current report artifacts for claim evidence."""
    text = _report_text(load_session())
    tokens = [token for token in str(claim).lower().split() if token]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    matches = [
        line
        for line in lines
        if not tokens or any(token in line.lower() for token in tokens)
    ]
    return "\n".join(matches[:6]) or "No matching report evidence found."


@mcp.tool()
def write_postmortem(period: str, notes: str) -> str:
    """Persist postmortem notes onto the current session."""
    session = load_session()
    rows = list(session.get("postmortem_notes", []))
    rows.append({"period": str(period).strip(), "notes": str(notes).strip()})
    session["postmortem_notes"] = rows
    save_session(session)
    kuzu_service().project_runtime_state(session)
    return f"Saved postmortem for {period}"


@mcp.tool()
def build_issue_brief(period: str) -> str:
    """Build a unified brief from report digest plus Kuzu runtime projection."""
    session = load_session()
    issue = current_issue(session)
    if period and issue["period"] != period:
        return kuzu_service().issue_brief(period)
    digest = str(session.get("shared_memory", {}).get("report_digest", "")).strip()
    graph_brief = kuzu_service().issue_brief(period or issue["period"])
    return "\n".join(part for part in (graph_brief, digest) if part)


def _report_text(session: dict) -> str:
    artifacts = dict(session.get("report_artifacts") or {})
    for key in ("markdown_path", "json_path"):
        resolved = _artifact_path(artifacts.get(key))
        if resolved and resolved.exists():
            return resolved.read_text(encoding="utf-8")
    return ""


def _artifact_path(raw_path: object) -> Path | None:
    if not raw_path:
        return None
    value = Path(str(raw_path))
    if value.is_absolute():
        return value
    data_root = str(os.environ.get("LOTTERY_DATA_ROOT", "")).strip()
    if not data_root:
        return value
    return Path(data_root) / value


if __name__ == "__main__":
    mcp.run(transport="stdio")
