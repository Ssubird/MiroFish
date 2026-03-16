"""World graph projection helpers for the lottery simulator."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


PHASE_ORDER = (
    "opening",
    "public_debate",
    "judge_synthesis",
    "purchase_committee",
    "settlement",
    "postmortem",
)
PHASE_LABELS = {
    "opening": "Opening",
    "public_debate": "Debate",
    "judge_synthesis": "Synthesis",
    "purchase_committee": "Purchase",
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
        or str(latest.get("period", "")).strip()
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


def _phase_nodes(
    nodes: dict[str, dict[str, Any]],
    session: dict[str, Any],
    period: str,
) -> dict[str, str]:
    phase_nodes = {}
    latest_summary = dict(session.get("latest_issue_summary", {}))
    purchase = dict(session.get("latest_purchase_plan", {}))
    settlement = list(session.get("settlement_history", []))
    for phase in PHASE_ORDER:
        node_id = f"phase:{phase}:{period}"
        phase_nodes[phase] = node_id
        nodes[node_id] = {
            "id": node_id,
            "label": PHASE_LABELS[phase],
            "node_type": "phase",
            "phase": phase,
            "period": period,
            "active": session.get("current_phase") == phase,
            "numbers": _phase_numbers(phase, latest_summary, purchase, settlement),
            "summary": _phase_summary(phase, latest_summary, purchase, settlement),
        }
    return phase_nodes


def _phase_numbers(
    phase: str,
    latest_summary: dict[str, Any],
    purchase: dict[str, Any],
    settlement: list[dict[str, Any]],
) -> list[int]:
    if phase in {"opening", "public_debate", "judge_synthesis"}:
        return list(latest_summary.get("primary_numbers", [])) + list(latest_summary.get("alternate_numbers", []))
    if phase == "purchase_committee":
        return list(purchase.get("primary_prediction", [])) + list(purchase.get("alternate_numbers", []))
    if phase == "settlement" and settlement:
        return list(settlement[-1].get("actual_numbers", []))
    return []


def _phase_summary(
    phase: str,
    latest_summary: dict[str, Any],
    purchase: dict[str, Any],
    settlement: list[dict[str, Any]],
) -> str:
    if phase == "purchase_committee":
        return f"{purchase.get('plan_type', '-')} / play {purchase.get('play_size', '-')}"
    if phase == "settlement" and settlement:
        item = settlement[-1]
        return f"hits={item.get('consensus_hits', '-')} / best={item.get('best_hits', '-')}"
    if phase == "postmortem" and settlement:
        return f"best strategies={', '.join(item for item in settlement[-1].get('best_strategy_ids', [])) or '-'}"
    return str(latest_summary.get("phase", "") if phase == latest_summary.get("phase") else "").strip()


def _event_edges(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    session: dict[str, Any],
    timeline_rows: list[dict[str, Any]],
    phase_nodes: dict[str, str],
    period: str,
) -> None:
    round_index = defaultdict(int)
    for row in timeline_rows:
        if str(row.get("period", "")).strip() not in {"", "-", period}:
            continue
        actor_id = str(row.get("actor_id", "")).strip()
        if not actor_id or actor_id in {"system", "world_runtime"}:
            continue
        source = f"agent:{actor_id}"
        event_type = str(row.get("event_type", "")).strip()
        if event_type == "prediction_post":
            _edge(edges, source, phase_nodes["opening"], "proposed")
        if event_type == "debate_post":
            round_no = int(row.get("metadata", {}).get("round", 1) or 1)
            debate_id = _debate_round_node_id(phase_nodes["public_debate"], round_no)
            _debate_round_node(nodes, debate_id, period, round_no)
            round_index[debate_id] += 1
            _edge(edges, source, debate_id, "revised_to")
            for target in row.get("metadata", {}).get("support_agent_ids", []) or []:
                _edge(edges, source, f"agent:{target}", "supports")
        if event_type == "purchase_proposal":
            _edge(edges, source, phase_nodes["purchase_committee"], "proposed")
        if event_type == "purchase_decision":
            _edge(edges, source, phase_nodes["purchase_committee"], "purchased_from")
    _attach_round_nodes_to_phase(phase_nodes["public_debate"], round_index, edges)


def _debate_round_node(
    nodes: dict[str, dict[str, Any]],
    node_id: str,
    period: str,
    round_no: int,
) -> None:
    if node_id in nodes:
        return
    nodes[node_id] = {
        "id": node_id,
        "label": f"Debate R{round_no}",
        "node_type": "debate_round",
        "phase": "public_debate",
        "period": period,
        "active": False,
        "numbers": [],
        "summary": f"Round {round_no}",
    }


def _attach_round_nodes_to_phase(
    phase_node_id: str,
    round_index: dict[str, int],
    edges: dict[str, dict[str, Any]],
) -> None:
    for node_id in round_index:
        _edge(edges, node_id, phase_node_id, "revised_to")


def _phase_edges(
    edges: dict[str, dict[str, Any]],
    session: dict[str, Any],
    phase_nodes: dict[str, str],
    period: str,
) -> None:
    _edge(edges, phase_nodes["opening"], phase_nodes["judge_synthesis"], "synthesized_into")
    _edge(edges, phase_nodes["public_debate"], phase_nodes["judge_synthesis"], "synthesized_into")
    _edge(edges, phase_nodes["purchase_committee"], phase_nodes["judge_synthesis"], "purchased_from")
    if _settlement_for_period(session, period):
        _edge(edges, phase_nodes["judge_synthesis"], phase_nodes["settlement"], "settled_by")
        _edge(edges, phase_nodes["settlement"], phase_nodes["postmortem"], "settled_by")


def _settlement_for_period(session: dict[str, Any], period: str) -> bool:
    return any(str(item.get("period", "")).strip() == period for item in session.get("settlement_history", []))


def _conflict_edges(edges: dict[str, dict[str, Any]], session: dict[str, Any]) -> None:
    numbers = {
        item["session_agent_id"]: tuple(int(value) for value in dict(session.get("agent_state", {})).get(item["session_agent_id"], {}).get("last_numbers", []))
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


def _debate_round_node_id(base_node_id: str, round_no: int) -> str:
    return f"{base_node_id}:round:{round_no}"


def _edge(
    edges: dict[str, dict[str, Any]],
    source: str,
    target: str,
    relation: str,
    weight: int = 1,
) -> None:
    edge_id = f"{source}->{relation}->{target}"
    edges[edge_id] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "weight": weight,
    }
