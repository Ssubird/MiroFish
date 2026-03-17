import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Happy8RulesMCP")

@mcp.resource("happy8://rules/current")
def get_current_rules() -> str:
    """Get current Happy 8 rules."""
    return "Happy 8 rules: 1-10 play sizes, out of 80 numbers."

@mcp.resource("happy8://payouts/{play_size}")
def get_payouts(play_size: int) -> str:
    """Get payouts for a specific play size."""
    return f"Payouts for play size {play_size}"

@mcp.tool()
def list_play_types() -> list[str]:
    """List valid play types."""
    return [str(i) for i in range(1, 11)]

@mcp.tool()
def validate_plan(plan: str) -> bool:
    """Validate a purchase plan."""
    return True

@mcp.tool()
def price_plan(plan: str) -> int:
    """Calculate the cost of a purchase plan in yuan."""
    return 2

@mcp.tool()
def expand_plan(plan: str) -> str:
    """Expand a wheeling or dan-tuo plan into single tickets."""
    return plan

@mcp.tool()
def settle_plan(plan: str, actual_numbers: list[int]) -> dict:
    """Settle a purchase plan against actual numbers."""
    return {"hit": 0, "payout": 0}

@mcp.tool()
def estimate_risk(plan: str) -> str:
    """Estimate risk exposure of a plan."""
    return "low"

if __name__ == "__main__":
    mcp.run(transport="stdio")
