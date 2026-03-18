"""Markdown rendering for fixed per-issue reports."""

from __future__ import annotations

from typing import Any

from .issue_report import GROUP_LABELS
from .report_markdown_support import number_line


def build_issue_report_markdown(report: dict[str, Any]) -> str:
    sections = dict(report.get("sections") or {})
    lines = [
        f"# {report.get('report_name', 'issue_report')}",
        "",
        *background_markdown(dict(sections.get("background") or {})),
        *raw_signals_markdown(dict(sections.get("raw_signals") or {})),
        *social_process_markdown(dict(sections.get("social_process") or {})),
        *purchase_comparison_markdown(dict(sections.get("purchase_comparison") or {})),
        *final_decision_markdown(dict(sections.get("final_decision") or {})),
        *postmortem_markdown(dict(sections.get("postmortem") or {})),
    ]
    return "\n".join(lines).strip() + "\n"


def background_markdown(section: dict[str, Any]) -> list[str]:
    config = dict(section.get("runtime_config") or {})
    participants = list(section.get("participants") or [])
    return [
        "## 1. 本期背景",
        "",
        f"- 最后已知期: `{section.get('last_known_issue', '-')}`",
        f"- 目标预测期: `{section.get('target_prediction_issue', '-')}`",
        f"- 风险可见开奖区间: {section.get('risk_visible_draw_window', '-')}",
        f"- 运行配置: `runtime={config.get('runtime_mode', '-')} / model={config.get('llm_model_name', '-')} / rounds={config.get('agent_dialogue_rounds', '-')} / live_interview={config.get('live_interview_enabled', '-')}`",
        f"- 参与 agent 列表: `{', '.join(_participant_label(item) for item in participants) or '-'}`",
        "",
    ]


def raw_signals_markdown(section: dict[str, Any]) -> list[str]:
    lines = ["## 2. 原始信号", ""]
    for key in ("data", "metaphysics", "hybrid"):
        lines.append(f"### {GROUP_LABELS[key]}")
        lines.extend(_signal_group_lines(list(section.get(key) or [])))
    return lines


def social_process_markdown(section: dict[str, Any]) -> list[str]:
    lines = ["## 3. 社交过程", ""]
    lines.extend(_string_block("谁引用了谁", section.get("references")))
    lines.extend(_string_block("谁反对了谁", section.get("oppositions")))
    lines.extend(_string_block("哪些号码被放大", section.get("amplified_numbers")))
    lines.extend(_string_block("哪些结构被警告为拥挤", section.get("crowded_structures")))
    return lines


def purchase_comparison_markdown(section: dict[str, Any]) -> list[str]:
    structure = dict(section.get("combination_structure") or {})
    return [
        "## 4. 购买方案对比",
        "",
        f"- 预算: `{section.get('budget_yuan', '-')}`",
        f"- 玩法: `{section.get('gameplay', '-')}`",
        f"- 组合结构: `{section.get('plan_type', '-')}` / {structure or '-'}",
        f"- purchase_chair 方案: `{number_line(section.get('purchase_chair_numbers', []))}`",
        f"- final decider 方案: `{number_line(section.get('official_numbers', []))}`",
        f"- 最终是否采纳购买建议: `{section.get('accepted_by_final_decider', False)}`",
        "",
    ]


def final_decision_markdown(section: dict[str, Any]) -> list[str]:
    return [
        "## 5. 最终决策",
        "",
        f"- final decider 选了什么: `{number_line(section.get('numbers', []))}`",
        f"- 备用号码: `{number_line(section.get('alternate_numbers', []))}`",
        f"- 为什么选: {section.get('why_selected', '-')}",
        f"- 为什么没选其他方案: {section.get('why_not_others', '-')}",
        f"- 采纳组别: `{', '.join(section.get('adopted_groups', [])) or '-'}`",
        "",
    ]


def postmortem_markdown(section: dict[str, Any]) -> list[str]:
    lines = [
        "## 6. 开奖后复盘",
        "",
        f"- 实际开奖号: `{number_line(section.get('actual_numbers', []))}`",
        f"- 各方案命中情况: 官方 `{section.get('official_hits', '-')}` / 购买 `{section.get('purchase_hits', '-')}`",
        f"- 各组最佳命中: `{', '.join(_best_group_line(item) for item in section.get('group_best_hits', [])) or '-'}`",
        f"- 盈亏 / ROI / payout: `{section.get('profit_yuan', '-')}` / `{section.get('roi', '-')}` / `{section.get('payout_yuan', '-')}`",
    ]
    lines.extend(_string_block("对下期的权重校准建议", section.get("weight_calibration_suggestions")))
    return lines


def _signal_group_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- 无。", ""]
    lines = []
    for item in rows:
        lines.append(
            f"- {item.get('display_name', item.get('strategy_id', '-'))} (`{item.get('strategy_id', '-')}`): "
            f"`{number_line(item.get('numbers', []))}` | {item.get('rationale', '-')}"
        )
    lines.append("")
    return lines


def _participant_label(item: dict[str, Any]) -> str:
    return f"{item.get('display_name', item.get('agent_id', '-'))}({item.get('group', '-')})"


def _best_group_line(item: dict[str, Any]) -> str:
    return f"{item.get('group', '-')}:{item.get('strategy_id', '-')}/{item.get('hits', '-')}"


def _string_block(title: str, rows: Any) -> list[str]:
    values = [str(item).strip() for item in list(rows or []) if str(item).strip()]
    lines = [f"### {title}", ""]
    if not values:
        return [*lines, "- 无。", ""]
    return [*lines, *(f"- {item}" for item in values), ""]
