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
    issue_rows = state.get('issue_history', []) or state.get('settlement_history', [])
    return [
        "### World State",
        "",
        f"- Recent Issues: `{world_issue_history(issue_rows)}`",
        f"- Trend Numbers: `{world_trends(state.get('trend_numbers', []))}`",
        f"- Public Posts: `{world_posts(state.get('public_posts', []))}`",
        f"- Interview History: `{world_interviews(state.get('interview_history', []))}`",
        "",
    ]


def live_interviews_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["### Live Interviews", ""]
    for item in rows:
        lines.extend(
            [
                f"- {item.get('actor_display_name', item.get('display_name', item.get('actor_id', '-')))} (`{item.get('actor_id', item.get('agent_id', '-'))}`)",
                f"- Numbers: `{number_line(item.get('numbers', []))}`",
                f"- Answer: {item.get('content', item.get('answer', '-'))}",
                "",
            ]
        )
    return lines


def world_timeline_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = ["### World Timeline", ""]
    for item in rows:
        lines.extend(
            [
                f"- `{item.get('phase', '-')}` / `{item.get('event_type', '-')}` / {item.get('actor_display_name', '-')}",
                f"- Numbers: `{number_line(item.get('numbers', []))}`",
                f"- Content: {item.get('content', '-')}",
                "",
            ]
        )
    return lines


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
