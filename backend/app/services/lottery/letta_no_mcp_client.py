"""Letta-backed world client that skips MCP tooling explicitly."""

from __future__ import annotations

from .letta_client import LettaClient


class LettaNoMcpClient(LettaClient):
    """Use Letta agents and memory, but disable MCP registration explicitly."""

    mcp_disabled = True
    runtime_backend = "letta_no_mcp"
