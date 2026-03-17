import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("WorldStateMCP")

@mcp.resource("market://current_issue")
def current_issue() -> str:
    return "Current open issue details"

@mcp.resource("market://feed")
def market_feed() -> str:
    return "Recent market posts and signals"

@mcp.resource("market://leaderboard")
def leaderboard() -> str:
    return "Top performing agents and personas"

@mcp.tool()
def publish_post(agent_id: str, content: str, group: str) -> str:
    """Publish a post to the market feed."""
    return f"Post published by {agent_id}"

@mcp.tool()
def reply_post(agent_id: str, target_post_id: str, content: str) -> str:
    """Reply to an existing post."""
    return f"Reply added by {agent_id}"

@mcp.tool()
def update_trust(source_agent: str, target_agent: str, delta: float) -> str:
    """Update trust score between agents."""
    return "Trust updated"

@mcp.tool()
def get_market_snapshot() -> dict:
    """Get an overview of the current market state."""
    return {"volume": 0, "sentiment": "neutral"}

if __name__ == "__main__":
    mcp.run(transport="stdio")
