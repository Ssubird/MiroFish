"""World graph projection helpers for the lottery simulator."""

from __future__ import annotations

from typing import Any


V1_PHASE_ORDER = (
    "opening",
    "public_debate",
    "judge_synthesis",
    "purchase_committee",
    "settlement",
    "postmortem",
)
V2_PHASE_ORDER = (
    "generator_opening",
    "social_propagation",
    "market_rerank",
    "plan_synthesis",
    "handbook_final_decision",
    "settlement",
    "postmortem",
)
PHASE_LABELS = {
    "opening": "Opening",
    "generator_opening": "Generator Opening",
    "public_debate": "Debate",
    "social_propagation": "Social Propagation",
    "judge_synthesis": "Judge Synthesis",
    "market_rerank": "Market Rerank",
    "purchase_committee": "Purchase Committee",
    "plan_synthesis": "Plan Synthesis",
    "handbook_final_decision": "Handbook Final Decision",
    "settlement": "Settlement",
    "postmortem": "Postmortem",
}
CONFLICT_THRESHOLD = 1


def build_world_graph(session: dict[str, Any], timeline_rows: list[dict[str, Any]]) -> dict[str, Any]:
    period = _graph_period(session)
    nodes = {}
    edges = {}
    _agent_nodes(nodes, session)
    phase_nodes = _phase_nodes(nodes, session, period)
    _event_edges(nodes, edges, session, timeline_rows, phase_nodes, period)
    _phase_edges(edges, session, phase_nodes, period)
    _conflict_edges(edges, session)
    return {
        "session_id": session["session_id"],
        "period": period,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "metrics": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "active_agents": len(session.get("active_agent_ids", [])),
        },
    }


def _graph_period(session: dict[str, Any]) -> str:
    latest = dict(session.get("latest_prediction", {}))
    return (
        str(session.get("current_period", "")).strip()
        or str(latest.get("predicted_period", latest.get("period", ""))).strip()
        or str((session.get("settlement_history") or [{}])[-1].get("period", "")).strip()
        or "-"
    )


def _agent_nodes(nodes: dict[str, dict[str, Any]], session: dict[str, Any]) -> None:
    state_rows = dict(session.get("agent_state", {}))
    active_ids = set(session.get("active_agent_ids", []))
    for agent in session.get("agents", []):
        state = dict(state_rows.get(agent["session_agent_id"], {}))
        node_id = f"agent:{agent['session_agent_id']}"
        nodes[node_id] = {
            "id": node_id,
            "label": agent["display_name"],
            "node_type": "agent",
            "group": agent.get("group", "-"),
            "role_kind": agent.get("role_kind", "-"),
            "active": agent["session_agent_id"] in active_ids,
            "recent_hits": list(state.get("recent_hits", []))[-3:],
            "numbers": list(state.get("last_numbers", []))[:8],
            "comment": str(state.get("last_comment", "")).strip(),
        }


def _phase_nodes(nodes: dict[str, dict[str, Any]], session: dict[str, Any], period: str) -> dict[str, str]:
    phase_nodes = {}
    latest_summary = dict(session.get("latest_issue_summary", {}))
    purchase = dict(session.get("latest_purchase_plan", {}))
    latest_prediction = dict(session.get("latest_prediction", {}))
    final_decision = dict(latest_prediction.get("final_decision") or {})
    settlement = list(session.get("settlement_history", []))
    for phase in _phase_order(session):
        node_id = f"phase:{phase}:{period}"
        phase_nodes[phase] = node_id
        nodes[node_id] = {
            "id": node_id,
            "label": PHASE_LABELS[phase],
            "node_type": "phase",
            "phase": phase,
            "period": period,
            "active": session.get("current_phase") == phase,
            "numbers": _phase_numbers(phase, latest_summary, purchase, final_decision, settlement),
            "summary": _phase_summary(phase, latest_summary, purchase, final_decision, settlement),
        }
    return phase_nodes


def _phase_numbers(phase: str, latest_summary: dict[str, Any], purchase: dict[str, Any], final_decision: dict[str, Any], settlement: list[dict[str, Any]]) -> list[int]:
    if phase in {"opening", "generator_opening", "public_debate", "social_propagation", "judge_synthesis", "market_rerank"}:
        return list(latest_summary.get("primary_numbers", [])) + list(latest_summary.get("alternate_numbers", []))
    if phase == "plan_synthesis":
        return list(purchase.get("primary_prediction", [])) + list(purchase.get("alternate_numbers", []))
    if phase == "handbook_final_decision":
        return list(final_decision.get("numbers", [])) + list(final_decision.get("alternate_numbers", []))
    if phase == "settlement" and settlement:
        return list(settlement[-1].get("actual_numbers", []))
    return []


def _phase_summary(phase: str, latest_summary: dict[str, Any], purchase: dict[str, Any], final_decision: dict[str, Any], settlement: list[dict[str, Any]]) -> str:
    if phase == "plan_synthesis":
        return f"{purchase.get('plan_type', '-')} / play {purchase.get('play_size', '-')}"
    if phase == "handbook_final_decision":
        return str(final_decision.get("rationale", "")).strip() or "Official final decision"
    if phase == "settlement" and settlement:
        item = settlement[-1]
        return f"official_hits={item.get('official_hits', '-')} / purchase_profit={item.get('purchase_profit', '-')}"
    return str(latest_summary.get("phase", "") if phase == latest_summary.get("phase") else "").strip()


def _event_edges(nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]], session: dict[str, Any], timeline_rows: list[dict[str, Any]], phase_nodes: dict[str, str], period: str) -> None:
    is_v2 = _is_v2_session(session)
    for row in timeline_rows:
        if str(row.get("period", "")).strip() not in {"", "-", period}:
            continue
        actor_id = str(row.get("actor_id", "")).strip()
        if not actor_id or actor_id in {"system", "world_runtime"}:
            continue
        source = f"agent:{actor_id}"
        event_type = str(row.get("event_type", "")).strip()
        if event_type == "prediction_post":
            _edge(edges, source, phase_nodes["generator_opening" if is_v2 else "opening"], "proposed")
        if event_type in {"live_interview", "social_post", "social_reply"} and is_v2:
            _edge(edges, source, phase_nodes["social_propagation"], "proposed")
        if event_type == "market_rank" and is_v2:
            _edge(edges, source, phase_nodes["market_rerank"], "ranked")
        if event_type == "purchase_decision":
            _edge(edges, source, phase_nodes["plan_synthesis" if is_v2 else "purchase_committee"], "purchased_from")
        if event_type == "official_prediction" and is_v2:
            _edge(edges, source, phase_nodes["handbook_final_decision"], "decided")


def _phase_edges(edges: dict[str, dict[str, Any]], session: dict[str, Any], phase_nodes: dict[str, str], period: str) -> None:
    if _is_v2_session(session):
        _edge(edges, phase_nodes["generator_opening"], phase_nodes["market_rerank"], "synthesized_into")
        _edge(edges, phase_nodes["social_propagation"], phase_nodes["market_rerank"], "synthesized_into")
        _edge(edges, phase_nodes["market_rerank"], phase_nodes["plan_synthesis"], "synthesized_into")
        _edge(edges, phase_nodes["plan_synthesis"], phase_nodes["handbook_final_decision"], "synthesized_into")
    else:
        _edge(edges, phase_nodes["opening"], phase_nodes["judge_synthesis"], "synthesized_into")
        _edge(edges, phase_nodes["public_debate"], phase_nodes["judge_synthesis"], "synthesized_into")
        _edge(edges, phase_nodes["purchase_committee"], phase_nodes["judge_synthesis"], "purchased_from")
    if _settlement_for_period(session, period):
        source_phase = "handbook_final_decision" if _is_v2_session(session) else "judge_synthesis"
        _edge(edges, phase_nodes[source_phase], phase_nodes["settlement"], "settled_by")
        _edge(edges, phase_nodes["settlement"], phase_nodes["postmortem"], "settled_by")


def _settlement_for_period(session: dict[str, Any], period: str) -> bool:
    return any(str(item.get("period", "")).strip() == period for item in session.get("settlement_history", []))


def _conflict_edges(edges: dict[str, dict[str, Any]], session: dict[str, Any]) -> None:
    numbers = {
        item["session_agent_id"]: tuple(
            int(value)
            for value in dict(session.get("agent_state", {})).get(item["session_agent_id"], {}).get("last_numbers", [])
        )
        for item in session.get("agents", [])
        if item.get("role_kind") == "strategy"
    }
    strategy_ids = sorted(numbers)
    for index, left in enumerate(strategy_ids):
        for right in strategy_ids[index + 1 :]:
            overlap = len(set(numbers[left]) & set(numbers[right]))
            if overlap > CONFLICT_THRESHOLD:
                continue
            _edge(edges, f"agent:{left}", f"agent:{right}", "conflicts_with", overlap)


def _phase_order(session: dict[str, Any]) -> tuple[str, ...]:
    return V2_PHASE_ORDER if _is_v2_session(session) else V1_PHASE_ORDER


def _is_v2_session(session: dict[str, Any]) -> bool:
    return str(session.get("runtime_mode", "")).strip() == "world_v2_market"


def _edge(edges: dict[str, dict[str, Any]], source: str, target: str, relation: str, weight: int = 1) -> None:
    edge_id = f"{source}->{relation}->{target}"
    edges[edge_id] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "weight": weight,
    }
