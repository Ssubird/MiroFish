"""Support helpers for lottery markdown reports."""

from __future__ import annotations


def coordination_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["### Coordination", ""]
    for stage in rows:
        lines.extend(coordination_stage(stage))
    return lines


def coordination_stage(stage: dict[str, object]) -> list[str]:
    lines = [f"#### {stage.get('title', stage.get('stage', '-'))}"]
    active = ", ".join(stage.get("active_strategy_ids", [])) or "-"
    groups = ", ".join(stage.get("active_groups", [])) or "-"
    lines.append(f"- Active Agents: `{active}`")
    lines.append(f"- Active Groups: `{groups}`")
    lines.append("")
    for item in stage.get("items", []):
        lines.extend(coordination_item(item))
    return lines


def coordination_item(item: dict[str, object]) -> list[str]:
    lines = [f"- {item.get('display_name', item.get('strategy_id', '-'))} (`{item.get('strategy_id', '-')}`)"]
    lines.append(f"- Group / Kind: `{item.get('group', '-')} / {item.get('kind', '-')}`")
    lines.append(f"- Numbers: `{number_line(item.get('numbers_after', item.get('numbers', [])))}`")
    if item.get("numbers_before"):
        lines.append(f"- Before: `{number_line(item['numbers_before'])}`")
    if item.get("comment"):
        lines.append(f"- Comment: {item['comment']}")
    if item.get("rationale"):
        lines.append(f"- Rationale: {item['rationale']}")
    if item.get("peer_strategy_ids"):
        lines.append(f"- Read Peers: `{', '.join(item['peer_strategy_ids'])}`")
    lines.append("")
    return lines


def social_state_section(state: dict[str, object]) -> list[str]:
    if not state:
        return []
    lines = ["### Social State", ""]
    for strategy_id, item in sorted(state.items()):
        lines.extend(
            [
                f"#### {item.get('display_name', strategy_id)} (`{strategy_id}`)",
                "",
                f"- Persona: {item.get('persona', '-')}",
                f"- Trust Network: `{', '.join(item.get('trust_network', [])) or '-'}`",
                f"- Post History: `{social_history(item.get('post_history', []), 'numbers')}`",
                f"- Revision History: `{social_history(item.get('revision_history', []), 'numbers_after')}`",
                "",
            ]
        )
    return lines


def world_state_section(state: dict[str, object]) -> list[str]:
    if not state:
        return []
    return [
        "### World State",
        "",
        f"- Recent Issues: `{world_issue_history(state.get('issue_history', []))}`",
        f"- Trend Numbers: `{world_trends(state.get('trend_numbers', []))}`",
        f"- Public Posts: `{world_posts(state.get('public_posts', []))}`",
        f"- Interview History: `{world_interviews(state.get('interview_history', []))}`",
        "",
    ]


def purchase_section(plan: dict[str, object]) -> list[str]:
    lines = ["### Purchase Plan", ""]
    if not plan:
        return [*lines, "- Not generated.", ""]
    lines.extend(purchase_header(plan))
    if plan.get("alternate_numbers"):
        lines.append(f"- Planner Alternate Numbers: `{number_line(plan.get('alternate_numbers', []))}`")
    if plan.get("reason"):
        return [*lines, f"- Reason: {plan['reason']}", ""]
    planner = plan.get("planner") or {}
    structure = plan.get("plan_structure") or {}
    lines.extend(
        [
            f"- Planner: `{planner.get('display_name', '-')}` / Model: `{planner.get('model', '-')}`",
            f"- Plan Type: `{plan.get('plan_type', planner.get('plan_type', '-'))}` / Style: `{planner.get('plan_style', '-')}`",
            f"- Trusted Strategies: `{', '.join(planner.get('trusted_strategy_ids', [])) or '-'}`",
            f"- Core Numbers: `{number_line(planner.get('core_numbers', []))}`",
            f"- Hedge Numbers: `{number_line(planner.get('hedge_numbers', []))}`",
            f"- Avoid Numbers: `{number_line(planner.get('avoid_numbers', []))}`",
            f"- Rationale: {planner.get('rationale', '-')}",
        ]
    )
    if planner.get("user_prompt_preview"):
        lines.append(f"- Planner Prompt Preview: {planner['user_prompt_preview']}")
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
        f"- Primary Prediction: `{number_line(plan.get('primary_prediction', []))}`",
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
        f"- Plan Type: `{item.get('plan_type', '-')}` / Style: `{item.get('plan_style', '-')}`",
        f"- Proposed Numbers: `{number_line(proposed_numbers(item))}`",
        f"- Trusted Strategies: `{', '.join(item.get('trusted_strategy_ids', [])) or '-'}`",
        f"- Rationale: {item.get('rationale', '-')}",
    ]
    if item.get("user_prompt_preview"):
        lines.append(f"- Prompt Preview: {item['user_prompt_preview']}")
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
            f"Plan `{item.get('plan_type', '-')}` / Support `{support}`"
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


def metadata_lines(metadata: dict[str, object]) -> list[str]:
    lines = []
    if metadata.get("focus"):
        lines.append(f"- Focus: `{', '.join(str(value) for value in metadata['focus'])}`")
    if metadata.get("trusted_strategy_ids"):
        lines.append(f"- Trusted Strategies: `{', '.join(metadata['trusted_strategy_ids'])}`")
    if metadata.get("sources"):
        lines.append(f"- Sources: `{', '.join(metadata['sources'])}`")
    if metadata.get("latest_dialogue_comment"):
        lines.append(f"- Latest Dialogue Comment: {metadata['latest_dialogue_comment']}")
    if metadata.get("user_prompt_preview"):
        lines.append(f"- Prompt Preview: {metadata['user_prompt_preview']}")
    if metadata.get("dialogue_user_prompt_preview"):
        lines.append(f"- Dialogue Prompt Preview: {metadata['dialogue_user_prompt_preview']}")
    return lines


def plan_structure_lines(structure: dict[str, object]) -> list[str]:
    lines = []
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
    if item.get("primary_ticket"):
        return list(item["primary_ticket"])
    if item.get("wheel_numbers"):
        return list(item["wheel_numbers"])
    numbers = list(item.get("banker_numbers", []))
    numbers.extend(number for number in item.get("drag_numbers", []) if number not in numbers)
    return numbers


def social_history(rows: list[dict[str, object]], number_key: str) -> str:
    if not rows:
        return "-"
    return " | ".join(f"{item.get('period', '-')}: {item.get(number_key, [])}" for item in rows[-3:])


def world_issue_history(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "-"
    return " | ".join(
        f"{item.get('period', '-')}: consensus={item.get('consensus_numbers', [])}, "
        f"actual={item.get('actual_numbers', [])}, best_hits={item.get('best_hits', '-')}"
        for item in rows[-3:]
    )


def world_trends(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "-"
    return ", ".join(f"{item.get('number', '-')}x{item.get('mentions', '-')}" for item in rows[:10])


def world_posts(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "-"
    return " | ".join(
        f"{item.get('period', '-')}/{item.get('strategy_id', '-')}: {item.get('numbers', [])}"
        for item in rows[-4:]
    )


def world_interviews(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "-"
    return " | ".join(
        f"{item.get('period', '-')}/{item.get('source_strategy_id', '-')}: {item.get('numbers', [])}"
        for item in rows[-3:]
    )


def number_line(numbers: list[object]) -> str:
    return ", ".join(str(value) for value in numbers) or "-"
