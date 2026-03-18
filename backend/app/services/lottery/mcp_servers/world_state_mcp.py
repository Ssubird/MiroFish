"""World state MCP server backed by the persistent world session store."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..world_models import WorldEvent, world_id, world_now
from .support import current_issue as current_issue_payload
from .support import kuzu_service, load_session, save_session, session_id, world_store


mcp = FastMCP("WorldStateMCP")


@mcp.resource("market://current_issue")
def current_issue() -> str:
    payload = current_issue_payload()
    return (
        f"period={payload['period']}\n"
        f"phase={payload['phase']}\n"
        f"status={payload['status']}\n"
        f"brief={payload['brief'] or '-'}"
    )


@mcp.resource("market://feed")
def market_feed() -> str:
    rows = world_store().list_events(session_id(), 0, 12, latest=True)["items"]
    lines = [
        f"- [{item.get('phase', '-')}] {item.get('actor_display_name', item.get('actor_id', '-'))}: {item.get('content', '')}"
        for item in rows
    ]
    return "\n".join(lines) or "- no market events yet"


@mcp.resource("market://leaderboard")
def leaderboard() -> str:
    session = load_session()
    rows = list((session.get("latest_prediction", {}) or {}).get("performance_context", []))
    lines = [
        f"- #{item.get('rank', '-')} {item.get('display_name', item.get('strategy_id', '-'))}: "
        f"objective={item.get('objective_score', '-')}, roi={item.get('strategy_roi', '-')}"
        for item in rows[:8]
    ]
    return "\n".join(lines) or "- no settled leaderboard yet"


@mcp.tool()
def publish_post(agent_id: str, content: str, group: str) -> str:
    session = load_session()
    event = _manual_event(session, "social_post", agent_id, content, {"group": group or "social"})
    world_store().append_events(session_id(), [event])
    _record_post(session, agent_id, "manual_social", content)
    save_session(session)
    kuzu_service().project_runtime_state(session)
    return event.event_id


@mcp.tool()
def reply_post(agent_id: str, target_post_id: str, content: str) -> str:
    session = load_session()
    event = _manual_event(
        session,
        "social_reply",
        agent_id,
        content,
        {"group": "social", "target_post_id": str(target_post_id).strip()},
    )
    world_store().append_events(session_id(), [event])
    _record_post(session, agent_id, "manual_reply", content)
    save_session(session)
    kuzu_service().project_runtime_state(session)
    return event.event_id


@mcp.tool()
def update_trust(source_agent: str, target_agent: str, delta: float) -> str:
    session = load_session()
    state = session.setdefault("agent_state", {}).setdefault(str(source_agent), {})
    trust_network = list(state.get("trust_network", []))
    target = str(target_agent).strip()
    if delta >= 0 and target not in trust_network:
        trust_network.append(target)
    if delta < 0 and target in trust_network:
        trust_network.remove(target)
    state["trust_network"] = trust_network
    save_session(session)
    kuzu_service().project_runtime_state(session)
    return f"{source_agent}->{target_agent}={delta}"


@mcp.tool()
def get_market_snapshot() -> dict:
    session = load_session()
    feed = world_store().list_events(session_id(), 0, 12, latest=True)
    return {
        "issue": current_issue_payload(session),
        "feed_events": feed["total"],
        "active_agents": len(session.get("active_agent_ids", [])),
        "top_influencers": kuzu_service().top_influencers(5),
    }


def _manual_event(session: dict, event_type: str, agent_id: str, content: str, metadata: dict) -> WorldEvent:
    agent = next((item for item in session.get("agents", []) if item.get("session_agent_id") == agent_id), None)
    display_name = agent.get("display_name", agent_id) if agent else agent_id
    return WorldEvent(
        event_id=world_id("evt"),
        session_id=session_id(),
        period=str(session.get("current_period") or session.get("latest_prediction", {}).get("period") or "-"),
        phase=str(session.get("current_phase") or "manual_social"),
        event_type=event_type,
        actor_id=str(agent_id),
        actor_display_name=display_name,
        content=str(content).strip(),
        created_at=world_now(),
        metadata=metadata,
    )


def _record_post(session: dict, agent_id: str, phase: str, content: str) -> None:
    state = session.setdefault("agent_state", {}).setdefault(str(agent_id), {})
    history = list(state.get("post_history", []))
    history.append(
        {
            "period": str(session.get("current_period") or session.get("latest_prediction", {}).get("period") or "-"),
            "phase": phase,
            "numbers": [],
            "comment": str(content).strip(),
        }
    )
    state["post_history"] = history
    state["last_phase"] = phase
    state["last_comment"] = str(content).strip()


if __name__ == "__main__":
    mcp.run(transport="stdio")
