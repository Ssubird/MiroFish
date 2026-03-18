"""Market-oriented markdown helpers for lottery reports."""

from __future__ import annotations

from collections.abc import Mapping

from .report_markdown_support import number_line


def judge_section(decision: dict[str, object]) -> list[str]:
    if not decision:
        return []
    return [
        "### Judge Projection (Compatibility)",
        "",
        f"- Reference Numbers: `{number_line(decision.get('primary_numbers', []))}`",
        f"- Hedge Pool: `{number_line(decision.get('alternate_numbers', []))}`",
        f"- Trusted Strategies: `{', '.join(decision.get('trusted_strategy_ids', [])) or '-'}`",
        f"- Rationale: {decision.get('rationale', '-')}",
        "",
    ]


def signal_outputs_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = [
        "### Signal Outputs",
        "",
        "| Agent | Regime | Play Bias | Structure | Top Numbers | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        lines.append(
            f"| {item.get('strategy_id', '-')} | {item.get('regime_label', '-')} | "
            f"{item.get('play_size_bias', '-')} | {item.get('structure_bias', '-')} | "
            f"{_signal_top_numbers(item)} | {', '.join(item.get('evidence_refs', [])) or '-'} |"
        )
    return [*lines, ""]


def market_synthesis_section(synthesis: dict[str, object]) -> list[str]:
    if not synthesis:
        return []
    reference_leg = dict(synthesis.get("reference_leg") or {})
    lines = [
        "### Market Synthesis",
        "",
        (
            f"- Reference Plan: `{synthesis.get('reference_plan_id', '-')}` / "
            f"Type: `{reference_leg.get('plan_type', '-')}` / "
            f"Play Size: `{reference_leg.get('play_size', '-')}`"
        ),
        f"- Reference Ticket: `{number_line(reference_leg.get('numbers', []))}`",
        f"- Hedge Pool: `{number_line(synthesis.get('hedge_pool', []))}`",
        (
            f"- Active Bettors: `{synthesis.get('active_bettor_count', '-')}` / "
            f"Market Volume: `{synthesis.get('total_market_volume_yuan', '-')}` yuan"
        ),
        f"- Trusted Strategies: `{', '.join(synthesis.get('trusted_strategy_ids', [])) or '-'}`",
        f"- Rationale: {synthesis.get('rationale', '-')}",
        "",
    ]
    lines.extend(consensus_score_section(synthesis.get("consensus_number_scores") or []))
    return lines


def consensus_score_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["#### Consensus Scores", "", "| Number | Score |", "| --- | --- |"]
    for item in rows[:15]:
        lines.append(f"| {item.get('number', '-')} | {item.get('score', '-')} |")
    return [*lines, ""]


def bet_plans_section(plans: dict[str, dict[str, object]]) -> list[str]:
    if not plans:
        return []
    lines = ["### Market Bet Plans", ""]
    for role_id, plan in sorted(plans.items()):
        lines.extend(bet_plan_lines(role_id, plan))
    return lines


def bet_plan_lines(role_id: str, plan: dict[str, object]) -> list[str]:
    reference_leg = _reference_leg(plan)
    lines = [
        f"#### {plan.get('display_name', role_id)} (`{role_id}`)",
        "",
        (
            f"- Plan Type: `{plan.get('plan_type', reference_leg.get('plan_type', '-'))}` / "
            f"Play Size: `{reference_leg.get('play_size', plan.get('play_size', '-'))}` / "
            f"Cost: `{plan.get('total_cost_yuan', '-')}` yuan / "
            f"Risk: `{plan.get('risk_exposure', '-')}`"
        ),
        f"- Reference Ticket: `{number_line(reference_leg.get('numbers', []))}`",
        f"- Trusted Strategies: `{', '.join(plan.get('trusted_strategy_ids', [])) or '-'}`",
        f"- Rationale: {plan.get('rationale', '-')}",
    ]
    lines.extend(plan_structure_lines(plan.get("plan_structure") or {}))
    lines.append("")
    return lines


def purchase_section(plan: dict[str, object]) -> list[str]:
    lines = ["### Purchase Plan", ""]
    if not plan:
        return [*lines, "- Not generated.", ""]
    lines.extend(purchase_header(plan))
    if plan.get("alternate_numbers"):
        lines.append(f"- Planner Hedge Pool: `{number_line(plan.get('alternate_numbers', []))}`")
    if plan.get("reason"):
        return [*lines, f"- Reason: {plan['reason']}", ""]
    planner = plan.get("planner") or {}
    structure = plan.get("plan_structure") or {}
    lines.extend(
        [
            f"- Planner: `{planner.get('display_name', '-')}` / Model: `{planner.get('model', '-')}`",
            f"- Plan Type: `{plan.get('plan_type', planner.get('plan_type', '-'))}` / Style: `{planner.get('plan_style', '-')}`",
            f"- Chosen Edge: {plan.get('chosen_edge', planner.get('chosen_edge', '-')) or '-'}",
            f"- Trusted Strategies: `{', '.join(planner.get('trusted_strategy_ids', [])) or '-'}`",
            f"- Core Numbers: `{number_line(planner.get('core_numbers', []))}`",
            f"- Hedge Numbers: `{number_line(planner.get('hedge_numbers', []))}`",
            f"- Avoid Numbers: `{number_line(planner.get('avoid_numbers', []))}`",
            f"- Rationale: {planner.get('rationale', '-')}",
        ]
    )
    if planner.get("user_prompt_preview"):
        lines.append(f"- Planner Prompt Preview: {planner['user_prompt_preview']}")
    elif planner.get("prompt_preview"):
        lines.append(f"- Planner Prompt Preview: {planner['prompt_preview']}")
    lines.extend(purchase_committee_section(plan.get("discussion_agents") or []))
    lines.extend(purchase_discussion_section(plan.get("discussion_trace") or []))
    lines.extend(plan_structure_lines(structure))
    lines.append("")
    lines.extend(trusted_strategy_section(plan.get("trusted_strategies") or []))
    lines.extend(ticket_section(plan.get("tickets") or []))
    lines.extend(history_section(plan.get("historical_backtest") or {}))
    return lines


def purchase_header(plan: dict[str, object]) -> list[str]:
    return [
        f"- Status: `{plan.get('status', '-')}`",
        (
            f"- Game: `{plan.get('game', '-')}` / Budget: `{plan.get('budget_yuan', '-')}` / "
            f"Tickets: `{plan.get('ticket_count', '-')}`"
        ),
        f"- Reference Ticket: `{number_line(plan.get('primary_prediction', []))}`",
    ]


def purchase_committee_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["#### Purchase Committee", ""]
    for item in rows:
        lines.extend(purchase_committee_item(item))
    return lines


def purchase_committee_item(item: dict[str, object]) -> list[str]:
    lines = [
        f"- {item.get('display_name', item.get('role_id', '-'))} (`{item.get('role_id', '-')}`)",
        f"- Plan Type: `{item.get('plan_type', '-')}` / Play Size: `{item.get('play_size', '-')}` / Style: `{item.get('plan_style', '-')}`",
        f"- Chosen Edge: {item.get('chosen_edge', '-') or '-'}",
        f"- Proposed Numbers: `{number_line(proposed_numbers(item))}`",
        f"- Trusted Strategies: `{', '.join(item.get('trusted_strategy_ids', [])) or '-'}`",
        f"- Rationale: {item.get('rationale', '-')}",
    ]
    if item.get("user_prompt_preview"):
        lines.append(f"- Prompt Preview: {item['user_prompt_preview']}")
    elif item.get("prompt_preview"):
        lines.append(f"- Prompt Preview: {item['prompt_preview']}")
    lines.append("")
    return lines


def purchase_discussion_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["#### Purchase Discussion", ""]
    for item in rows:
        lines.extend(purchase_discussion_item(item))
    return lines


def purchase_discussion_item(item: dict[str, object]) -> list[str]:
    support = ", ".join(item.get("support_role_ids", [])) or "-"
    return [
        (
            f"- Round `{item.get('round', '-')}` / "
            f"{item.get('display_name', item.get('role_id', '-'))} / "
            f"Plan `{item.get('plan_type', '-')}` / Play `{item.get('play_size', '-')}` / Support `{support}`"
        ),
        f"- Numbers: `{number_line(proposed_numbers(item))}`",
        f"- Comment: {item.get('comment', '-')}",
        "",
    ]


def trusted_strategy_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["#### Trusted Strategies", "", "| Rank | Agent | Objective | Avg | ROI | Numbers |", "| --- | --- | --- | --- | --- | --- |"]
    for item in rows:
        lines.append(
            f"| {item.get('rank', '-')} | {item['display_name']} (`{item['strategy_id']}`) | "
            f"{float(item.get('objective_score', 0.0)):.4f} | {float(item.get('average_hits', 0.0)):.4f} | "
            f"{float(item.get('strategy_roi', 0.0)):.4f} | {number_line(item.get('numbers', []))} |"
        )
    return [*lines, ""]


def ticket_section(rows: list[dict[str, object]]) -> list[str]:
    lines = ["#### Tickets", ""]
    for ticket in rows:
        lines.append(f"- #{ticket['index']}: `{number_line(ticket.get('numbers', []))}`")
    return [*lines, ""]


def history_section(history: dict[str, object]) -> list[str]:
    if not history:
        return []
    lines = [
        "#### Historical Replay",
        "",
        f"- Total Cost: `{history.get('total_cost', '-')}`",
        f"- Total Payout: `{history.get('total_payout', '-')}`",
        f"- Net Profit: `{history.get('net_profit', '-')}`",
        f"- ROI: `{history.get('roi', '-')}`",
        f"- Winning Issues: `{history.get('winning_issues', '-')}`",
        "",
        "| Period | Plan Type | Profit | Payout | Trusted Strategies |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in history.get("recent_issue_profit", []):
        trusted = ", ".join(item.get("trusted_strategy_ids", [])) or "-"
        lines.append(
            f"| {item['period']} | {item.get('plan_type', '-')} | {item['profit']} | {item['payout']} | {trusted} |"
        )
    return [*lines, ""]


def plan_structure_lines(structure: dict[str, object]) -> list[str]:
    lines = []
    if structure.get("portfolio_legs"):
        lines.append(f"- Portfolio Legs: `{len(structure.get('portfolio_legs', []))}`")
        for leg in structure.get("portfolio_legs", []):
            lines.extend(_portfolio_leg_lines(leg))
        if structure.get("combination_count") is not None:
            lines.append(f"- Total Ticket Count: `{structure.get('combination_count')}`")
        return lines
    if structure.get("primary_ticket"):
        lines.append(f"- Primary Ticket: `{number_line(structure['primary_ticket'])}`")
    if structure.get("wheel_numbers"):
        lines.append(f"- Wheel Numbers: `{number_line(structure['wheel_numbers'])}`")
    if structure.get("banker_numbers"):
        lines.append(f"- Banker Numbers: `{number_line(structure['banker_numbers'])}`")
    if structure.get("drag_numbers"):
        lines.append(f"- Drag Numbers: `{number_line(structure['drag_numbers'])}`")
    if structure.get("combination_count") is not None:
        lines.append(f"- Combination Count: `{structure.get('combination_count')}`")
    return lines


def proposed_numbers(item: dict[str, object]) -> list[object]:
    if item.get("portfolio_legs"):
        return _portfolio_numbers(item.get("portfolio_legs", []))
    if item.get("primary_ticket"):
        return list(item["primary_ticket"])
    if item.get("wheel_numbers"):
        return list(item["wheel_numbers"])
    numbers = list(item.get("banker_numbers", []))
    numbers.extend(number for number in item.get("drag_numbers", []) if number not in numbers)
    return numbers


def _portfolio_leg_lines(leg: dict[str, object]) -> list[str]:
    label = leg.get("play_label", f"选{leg.get('play_size', '-')}")
    lines = [
        (
            f"- Leg `{leg.get('index', '-')}` / Type `{leg.get('plan_type', '-')}` / "
            f"Play `{label}` / Tickets `{leg.get('ticket_count', leg.get('combination_count', '-'))}`"
        )
    ]
    if leg.get("tickets"):
        lines.append(f"- Leg Ticket Grid: `{number_line(leg.get('tickets', []))}`")
    if leg.get("wheel_numbers"):
        lines.append(f"- Leg Wheel Numbers: `{number_line(leg.get('wheel_numbers', []))}`")
    if leg.get("banker_numbers"):
        lines.append(f"- Leg Banker Numbers: `{number_line(leg.get('banker_numbers', []))}`")
    if leg.get("drag_numbers"):
        lines.append(f"- Leg Drag Numbers: `{number_line(leg.get('drag_numbers', []))}`")
    return lines


def _portfolio_numbers(legs: list[dict[str, object]]) -> list[object]:
    numbers = []
    for leg in legs:
        for value in proposed_numbers(leg):
            if value not in numbers:
                numbers.append(value)
    return numbers


def _signal_top_numbers(item: Mapping[str, object]) -> str:
    raw_scores = item.get("number_scores") or {}
    if not isinstance(raw_scores, Mapping):
        return "-"
    ranked = sorted(
        ((int(number), float(score)) for number, score in raw_scores.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return ", ".join(str(number) for number, _ in ranked[:6]) or "-"


def _reference_leg(plan: Mapping[str, object]) -> dict[str, object]:
    legs = plan.get("legs") or []
    if isinstance(legs, list) and legs:
        first = legs[0]
        if isinstance(first, Mapping):
            return {
                "plan_type": first.get("plan_type", plan.get("plan_type", "-")),
                "play_size": first.get("play_size", plan.get("play_size", "-")),
                "numbers": list(first.get("numbers", [])),
            }
    return {
        "plan_type": plan.get("plan_type", "-"),
        "play_size": plan.get("play_size", "-"),
        "numbers": list(plan.get("primary_prediction", [])),
    }
