"""Happy 8 rule and settlement MCP server."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from ..happy8_rules import ALLOWED_PLAY_SIZES, TICKET_COST_YUAN, play_rule, ticket_payout
from ..purchase_structures import planner_structure
from ..world_support import purchase_rule_block


DEFAULT_PICK_SIZE = 5
mcp = FastMCP("Happy8RulesMCP")


@mcp.resource("happy8://rules/current")
def get_current_rules() -> str:
    """Get the current Happy 8 purchase rules."""
    return purchase_rule_block()


@mcp.resource("happy8://payouts/{play_size}")
def get_payouts(play_size: int) -> str:
    """Get the payout ladder for a given play size."""
    rule = play_rule(play_size)
    payouts = ", ".join(f"hit {hits} -> {amount}" for hits, amount in sorted(rule.payouts.items()))
    return f"{rule.label}: {payouts}"


@mcp.tool()
def list_play_types() -> list[str]:
    """List valid Happy 8 play sizes."""
    return [str(item) for item in ALLOWED_PLAY_SIZES]


@mcp.tool()
def validate_plan(plan: str) -> bool:
    """Validate a purchase plan payload."""
    payload = _plan_payload(plan)
    _plan_structure(payload)
    return True


@mcp.tool()
def price_plan(plan: str) -> int:
    """Calculate the ticket cost of a plan."""
    structure = _plan_structure(_plan_payload(plan))
    return len(structure.tickets) * TICKET_COST_YUAN


@mcp.tool()
def expand_plan(plan: str) -> str:
    """Expand a plan into concrete tickets."""
    payload = _plan_payload(plan)
    structure = _plan_structure(payload)
    return json.dumps(
        {
            "plan_type": structure.plan_type,
            "play_size": structure.play_size,
            "ticket_count": len(structure.tickets),
            "tickets": [list(ticket) for ticket in structure.tickets],
            "summary": structure.summary,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def settle_plan(plan: str, actual_numbers: list[int]) -> dict:
    """Settle a plan against the actual draw numbers."""
    structure = _plan_structure(_plan_payload(plan))
    actual = {int(value) for value in actual_numbers}
    tickets = [tuple(int(value) for value in ticket) for ticket in structure.tickets]
    payout = 0.0
    breakdown = []
    for index, ticket in enumerate(tickets, start=1):
        hits = len(actual & set(ticket))
        ticket_reward = ticket_payout(len(ticket), hits)
        payout += ticket_reward
        breakdown.append(
            {
                "ticket_index": index,
                "numbers": list(ticket),
                "hits": hits,
                "payout_yuan": ticket_reward,
            }
        )
    total_cost = len(tickets) * TICKET_COST_YUAN
    return {
        "ticket_count": len(tickets),
        "total_cost_yuan": total_cost,
        "total_payout_yuan": payout,
        "profit_yuan": payout - total_cost,
        "tickets": breakdown,
    }


@mcp.tool()
def estimate_risk(plan: str) -> str:
    """Estimate risk exposure from the structure itself."""
    payload = _plan_payload(plan)
    structure = _plan_structure(payload)
    if structure.plan_type == "portfolio":
        return "balanced"
    if structure.plan_type == "wheel":
        return "broad"
    if structure.plan_type == "dan_tuo":
        return "aggressive"
    if len(structure.tickets) >= 6:
        return "spread"
    return "focused"


def _plan_payload(plan: str) -> dict:
    try:
        payload = json.loads(plan)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Happy 8 plan JSON: {plan}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Happy 8 plan must be a JSON object")
    return payload


def _plan_structure(payload: dict):
    default_pick_size = int(payload.get("play_size", DEFAULT_PICK_SIZE) or DEFAULT_PICK_SIZE)
    max_tickets = max(int(payload.get("max_tickets", 100) or 100), 1)
    return planner_structure(payload, default_pick_size, max_tickets)


if __name__ == "__main__":
    mcp.run(transport="stdio")
