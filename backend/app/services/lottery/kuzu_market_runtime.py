"""Runtime projection helpers for the Kuzu market graph."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .world_v2_market import reference_leg_payload


def build_runtime_projection(session: dict[str, Any]) -> dict[str, object]:
    current_round = dict(session.get("current_round", {}))
    latest_prediction = dict(session.get("latest_prediction", {}))
    issue_period = str(
        current_round.get("target_period")
        or latest_prediction.get("period")
        or session.get("current_period")
        or "-"
    ).strip()
    issue_id = f"draw:{issue_period}"
    issue_text = str(session.get("shared_memory", {}).get("current_issue", "")).strip()
    agents = [_agent_row(item) for item in session.get("agents", [])]
    signal_outputs = list(current_round.get("signal_outputs", latest_prediction.get("signal_outputs", [])))
    bet_plans = dict(current_round.get("bet_plans", latest_prediction.get("bet_plans", {})))
    final_plan = dict(current_round.get("final_plan", latest_prediction.get("purchase_plan", {})))
    market_synthesis = dict(current_round.get("plan_synthesis", latest_prediction.get("market_synthesis", {})))
    trust_edges = _trust_edges(session)
    signals = _signal_rows(issue_period, signal_outputs)
    plans = _plan_rows(issue_period, bet_plans, final_plan)
    return {
        "issue": {"id": issue_id, "period": issue_period, "text": issue_text},
        "agents": agents,
        "signals": signals,
        "bet_plans": plans,
        "numbers": _number_rows(signals, plans),
        "posted_signal_edges": _posted_signal_edges(signals),
        "signal_issue_edges": [{"signal_id": item["id"], "issue_id": issue_id, "weight": 1.0} for item in signals],
        "scores_number_edges": _signal_number_edges(signals),
        "trust_edges": trust_edges,
        "follow_edges": _follow_edges(plans, market_synthesis),
        "market_synthesis": market_synthesis,
        "settlement_history": list(session.get("settlement_history", [])),
        "round_history": list(session.get("round_history", [])),
    }


def search_projection(projection: dict[str, Any], query: str, limit: int) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    rows = []
    for section in ("agents", "signals", "bet_plans"):
        for item in projection.get(section, []):
            text = " ".join(str(item.get(key, "")) for key in ("id", "display_name", "strategy_id", "persona_id", "comment", "rationale", "regime_label"))
            score = _match_score(tokens, text)
            if score <= 0:
                continue
            rows.append({"section": section, "score": score, **item})
    rows.sort(key=lambda item: (-item["score"], item["id"]))
    return rows[: max(limit, 1)]


def similar_projection_issues(projection: dict[str, Any], period: str, limit: int) -> list[dict[str, Any]]:
    settlements = list(projection.get("settlement_history", []))
    rows = []
    for item in settlements:
        current_period = str(item.get("period", "")).strip()
        if not current_period or current_period == period:
            continue
        consensus = tuple(int(value) for value in item.get("consensus_numbers", [])[:10])
        rows.append(
            {
                "period": current_period,
                "consensus_numbers": list(consensus),
                "actual_numbers": list(item.get("actual_numbers", [])),
                "consensus_hits": int(item.get("consensus_hits", 0) or 0),
            }
        )
    rows.sort(key=lambda item: (-item["consensus_hits"], item["period"]), reverse=False)
    return rows[: max(limit, 1)]


def projection_top_influencers(projection: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    incoming = Counter()
    for edge in projection.get("trust_edges", []):
        incoming[str(edge.get("target_id", ""))] += float(edge.get("weight", 1.0) or 1.0)
    for edge in projection.get("follow_edges", []):
        incoming[str(edge.get("target_id", ""))] += float(edge.get("weight", 1.0) or 1.0)
    agents = {item["id"]: item for item in projection.get("agents", [])}
    rows = []
    for agent_id, score in incoming.most_common(max(limit, 1)):
        item = agents.get(agent_id)
        if not item:
            continue
        rows.append(
            {
                "agent_id": agent_id,
                "display_name": item.get("display_name", agent_id),
                "group": item.get("group", "-"),
                "influence_score": round(score, 4),
            }
        )
    return rows


def projection_factions(projection: dict[str, Any]) -> list[dict[str, Any]]:
    graph = defaultdict(set)
    for edge in projection.get("trust_edges", []):
        source = str(edge.get("source_id", "")).strip()
        target = str(edge.get("target_id", "")).strip()
        if not source or not target:
            continue
        graph[source].add(target)
        graph[target].add(source)
    agents = {item["id"]: item for item in projection.get("agents", [])}
    seen = set()
    factions = []
    for agent_id in sorted(agents):
        if agent_id in seen:
            continue
        stack = [agent_id]
        members = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            members.append(current)
            stack.extend(sorted(graph.get(current, set()) - seen))
        factions.append(
            {
                "faction": f"cluster_{len(factions) + 1}",
                "members": [
                    {
                        "agent_id": member,
                        "display_name": agents.get(member, {}).get("display_name", member),
                        "group": agents.get(member, {}).get("group", "-"),
                    }
                    for member in members
                ],
            }
        )
    return factions


def projection_market_crowding(projection: dict[str, Any], numbers: list[int]) -> float:
    target = {int(value) for value in numbers}
    if not target:
        return 0.0
    plans = list(projection.get("bet_plans", []))
    if not plans:
        return 0.0
    covered = 0
    for plan in plans:
        leg_numbers = {int(value) for value in plan.get("numbers", [])}
        if target & leg_numbers:
            covered += 1
    return round(covered / len(plans), 4)


def projection_issue_brief(projection: dict[str, Any], period: str | None = None) -> str:
    issue = dict(projection.get("issue", {}))
    if period and str(issue.get("period", "")).strip() != period:
        return f"No projected issue found for {period}."
    signals = list(projection.get("signals", []))
    plans = list(projection.get("bet_plans", []))
    lines = [
        f"Target period: {issue.get('period', '-')}",
        f"Issue brief: {issue.get('text', '-')}",
        "Signals:",
    ]
    lines.extend(
        f"- {item.get('strategy_id', '-')}: top_numbers={item.get('top_numbers', [])}, regime={item.get('regime_label', '-')}"
        for item in signals[:6]
    )
    lines.append("Bet plans:")
    lines.extend(
        f"- {item.get('display_name', item.get('persona_id', '-'))}: type={item.get('plan_type', '-')}, numbers={item.get('numbers', [])}"
        for item in plans[:6]
    )
    return "\n".join(lines)


def _agent_row(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(agent.get("session_agent_id", "")).strip(),
        "display_name": str(agent.get("display_name", "")).strip(),
        "group": str(agent.get("group", "")).strip(),
        "role_kind": str(agent.get("role_kind", "")).strip(),
    }


def _signal_rows(period: str, signal_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in signal_outputs:
        strategy_id = str(item.get("strategy_id", "")).strip()
        if not strategy_id:
            continue
        scores = item.get("number_scores") or {}
        top_numbers = [
            int(number)
            for number, _ in sorted(
                ((int(key), float(value)) for key, value in scores.items()),
                key=lambda row: (-row[1], row[0]),
            )[:10]
        ]
        rows.append(
            {
                "id": f"signal:{period}:{strategy_id}",
                "strategy_id": strategy_id,
                "comment": str(item.get("public_post", "")).strip(),
                "regime_label": str(item.get("regime_label", "")).strip(),
                "number_scores": {str(key): float(value) for key, value in scores.items()},
                "top_numbers": top_numbers,
            }
        )
    return rows


def _plan_rows(period: str, bet_plans: dict[str, dict[str, Any]], final_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for role_id, plan in bet_plans.items():
        leg = reference_leg_payload(plan)
        rows.append(
            {
                "id": f"bet:{period}:{role_id}",
                "persona_id": role_id,
                "display_name": str(plan.get("display_name", role_id)).strip(),
                "plan_type": str(plan.get("plan_type", "")).strip(),
                "play_size": int(plan.get("play_size", 0) or 0),
                "numbers": list(leg.get("numbers", [])),
                "trusted_strategy_ids": [str(value) for value in plan.get("trusted_strategy_ids", [])],
                "rationale": str(plan.get("rationale", "")).strip(),
                "total_cost_yuan": int(plan.get("total_cost_yuan", 0) or 0),
            }
        )
    if final_plan:
        leg = reference_leg_payload(final_plan)
        rows.append(
            {
                "id": f"bet:{period}:purchase_chair",
                "persona_id": "purchase_chair",
                "display_name": str(final_plan.get("display_name", "purchase_chair")).strip(),
                "plan_type": str(final_plan.get("plan_type", "")).strip(),
                "play_size": int(final_plan.get("play_size", 0) or 0),
                "numbers": list(leg.get("numbers", [])),
                "trusted_strategy_ids": [str(value) for value in final_plan.get("trusted_strategy_ids", [])],
                "rationale": str(final_plan.get("rationale", "")).strip(),
                "total_cost_yuan": int(final_plan.get("total_cost_yuan", 0) or 0),
            }
        )
    return rows


def _number_rows(signals: list[dict[str, Any]], plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = set()
    for signal in signals:
        values.update(int(key) for key in signal.get("number_scores", {}))
    for plan in plans:
        values.update(int(value) for value in plan.get("numbers", []))
    return [{"id": f"number:{value}", "value": value} for value in sorted(values)]


def _posted_signal_edges(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"source_id": item["strategy_id"], "signal_id": item["id"], "weight": 1.0}
        for item in signals
    ]


def _signal_number_edges(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for signal in signals:
        for number, score in signal.get("number_scores", {}).items():
            rows.append(
                {
                    "signal_id": signal["id"],
                    "number_id": f"number:{int(number)}",
                    "weight": float(score),
                }
            )
    return rows


def _trust_edges(session: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for source_id, state in dict(session.get("agent_state", {})).items():
        trust_network = list(state.get("trust_network", []))
        for target_id in trust_network:
            rows.append(
                {
                    "source_id": str(source_id),
                    "target_id": str(target_id),
                    "weight": 1.0,
                }
            )
    return rows


def _follow_edges(plans: list[dict[str, Any]], market_synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    reference_plan_id = str(market_synthesis.get("reference_plan_id", "")).strip()
    for plan in plans:
        for strategy_id in plan.get("trusted_strategy_ids", []):
            rows.append(
                {
                    "source_id": plan["id"],
                    "target_id": str(strategy_id),
                    "weight": 1.0,
                }
            )
        if reference_plan_id and plan.get("persona_id") == reference_plan_id:
            rows.append(
                {
                    "source_id": plan["id"],
                    "target_id": "purchase_chair",
                    "weight": 1.0,
                }
            )
    return rows


def _tokens(query: str) -> list[str]:
    return [token for token in str(query).lower().split() if token]


def _match_score(tokens: list[str], text: str) -> int:
    haystack = str(text).lower()
    return sum(1 for token in tokens if token in haystack) if tokens else 1
