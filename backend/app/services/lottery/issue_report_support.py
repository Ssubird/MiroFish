"""Helper functions shared by issue-report builders."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .report_markdown_support import number_line


WARNING_TOKENS = ("risk", "crowd", "crowded", "avoid", "warning", "拥挤", "风险", "避开")
MAX_SOCIAL_LINES = 8
MAX_REVIEW_LINES = 4


def reference_lines(events: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in events[:MAX_SOCIAL_LINES]:
        meta = dict(item.get("metadata") or {})
        refs = [*meta.get("trusted_strategy_ids", []), *meta.get("support_agent_ids", [])]
        if refs:
            lines.append(f"{actor_name(item)} 引用了 {', '.join(dedupe_strings(refs))}")
    return lines or ["无明确引用记录。"]


def opposition_lines(
    social_events: list[dict[str, Any]],
    judge_events: list[dict[str, Any]],
) -> list[str]:
    lines = [warning_line(item) for item in [*social_events, *judge_events]]
    filtered = [item for item in lines if item]
    return filtered[:MAX_SOCIAL_LINES] or ["无明确反对记录。"]


def amplified_number_lines(events: list[dict[str, Any]]) -> list[str]:
    counter = Counter(int(number) for item in events for number in item.get("numbers", []))
    rows = [f"{number} x {count}" for number, count in counter.most_common(MAX_SOCIAL_LINES)]
    return rows or ["无明显被放大的号码。"]


def crowded_structure_lines(
    social_events: list[dict[str, Any]],
    judge_events: list[dict[str, Any]],
) -> list[str]:
    lines = []
    for item in [*social_events, *judge_events]:
        meta = dict(item.get("metadata") or {})
        comment = str(item.get("content", "") or item.get("comment", "")).strip()
        structure = str(meta.get("structure_bias", "")).strip()
        if structure and is_warning_text(comment):
            lines.append(f"{actor_name(item)} 警告 `{structure}` 结构可能拥挤: {comment}")
    return lines[:MAX_SOCIAL_LINES] or ["暂无明确的拥挤结构警告。"]


def group_best_hits(settlement: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for strategy_id, item in dict(settlement.get("strategy_issue_results") or {}).items():
        group = str(item.get("group", "")).strip() or "-"
        current = grouped.get(group)
        if current and int(current.get("hits", 0) or 0) >= int(item.get("hits", 0) or 0):
            continue
        grouped[group] = {
            "group": group,
            "strategy_id": strategy_id,
            "hits": int(item.get("hits", 0) or 0),
            "numbers": list(item.get("predicted_numbers", [])),
        }
    return [grouped[key] for key in sorted(grouped)]


def weight_calibration_lines(item: dict[str, Any], round_state: dict[str, Any]) -> list[str]:
    rows = []
    for event in list(round_state.get("postmortem_events") or [])[:MAX_REVIEW_LINES]:
        comment = str(event.get("content", "")).strip()
        if comment:
            rows.append(f"{actor_name(event)}: {comment}")
    if rows:
        return rows
    summary = str(dict(item.get("latest_review") or {}).get("summary", "")).strip()
    return [summary] if summary else ["暂无校准建议。"]


def why_not_others(decision: dict[str, Any], round_state: dict[str, Any]) -> str:
    risk_note = str(decision.get("risk_note", "")).strip()
    if risk_note:
        return risk_note
    if bool(decision.get("accepted_purchase_recommendation", False)):
        return "最终方案直接采用了 purchase_chair 的主建议，没有再额外引入第二个裁决代理。"
    purchase_numbers = number_line(reference_numbers(dict(round_state.get("final_plan") or {})))
    return f"最终方案没有直接照搬 purchase_chair `{purchase_numbers}`，因为需要进一步控制拥挤与分散风险。"


def reference_numbers(plan: dict[str, Any]) -> list[Any]:
    primary = list(plan.get("primary_ticket", []))
    if primary:
        return primary
    legs = list(plan.get("legs", []))
    if not legs:
        return []
    return list(dict(legs[0]).get("numbers", []))


def warning_line(item: dict[str, Any]) -> str:
    actor_id = str(item.get("actor_id", "")).strip()
    comment = str(item.get("content", "") or item.get("comment", "")).strip()
    if "risk" not in actor_id and not is_warning_text(comment):
        return ""
    numbers = number_line(item.get("numbers", []))
    return f"{actor_name(item)} 对 `{numbers}` 提出了反对或警告: {comment or '-'}"


def is_warning_text(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in WARNING_TOKENS)


def dedupe_strings(values: list[Any]) -> list[str]:
    seen = set()
    rows = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def actor_name(item: dict[str, Any]) -> str:
    return str(
        item.get("actor_id", "")
        or item.get("agent_id", "")
        or item.get("actor_display_name", "")
        or item.get("display_name", "-")
    ).strip()


def top_board_numbers(item: dict[str, Any]) -> list[int]:
    scores = item.get("number_scores") or {}
    pairs = [(int(number), float(score)) for number, score in scores.items()]
    pairs.sort(key=lambda row: (-row[1], row[0]))
    return [number for number, _ in pairs[:6]]
