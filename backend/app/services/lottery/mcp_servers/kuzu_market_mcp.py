"""Kuzu-backed market query MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .support import kuzu_service


mcp = FastMCP("KuzuMarketMCP")


@mcp.tool()
def search_docs(query: str, limit: int = 5) -> list[dict]:
    """Search the runtime market projection."""
    return kuzu_service().search_market(query, limit)


@mcp.tool()
def similar_issues(period: str, limit: int = 3) -> list[dict]:
    """Find historically similar projected issues."""
    return kuzu_service().similar_issues(period, limit)


@mcp.tool()
def top_influencers(limit: int = 5) -> list[dict]:
    """Get the most influential agents from the projected trust graph."""
    return kuzu_service().top_influencers(limit)


@mcp.tool()
def detect_factions() -> list[dict]:
    """Detect trust-based factions among agents."""
    return kuzu_service().detect_factions()


@mcp.tool()
def market_crowding(numbers: list[int]) -> float:
    """Measure how crowded the supplied numbers are among current market plans."""
    return kuzu_service().market_crowding(numbers)


if __name__ == "__main__":
    mcp.run(transport="stdio")
