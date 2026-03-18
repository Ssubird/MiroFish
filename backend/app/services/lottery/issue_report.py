"""Fixed per-issue report payload builders."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .report_markdown_support import number_line

GROUP_LABELS = {
    "data": "数据组信号摘要",
    "metaphysics": "玄学组信号摘要",
    "hybrid": "混合组信号摘要",
}
WARNING_TOKENS = ("risk", "crowd", "crowded", "avoid", "warning", "拥挤", "风险", "避开")
MAX_SIGNAL_LINES = 6
MAX_SOCIAL_LINES = 8
MAX_REVIEW_LINES = 4


def issue_report_stem(period: str) -> str:
    text = str(period).strip()
    suffix = text[-3:] if len(text) >= 3 else text.zfill(3)
    return f"issue_{suffix}_report"


def build_issue_report_payload(
    item: dict[str, Any],
    session: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    period = str(item.get("predicted_period", "")).strip()
    round_state = _round_state_for_period(session, period)
    settlement = _settlement_for_period(session, period)
    report = {
        "report_name": issue_report_stem(period),
        "issue_suffix": issue_report_stem(period).split("_")[1],
        "predicted_period": period,
        "visible_through_period": str(item.get("visible_through_period", "")).strip(),
        "sections": {
            "background": _background_section(item, session, evaluation, round_state),
            "raw_signals": _raw_signals_section(round_state),
            "social_process": _social_process_section(round_state),
            "purchase_comparison": _purchase_comparison_section(item, session, round_state),
            "final_decision": _final_decision_section(item, round_state),
            "postmortem": _postmortem_section(item, round_state, settlement),
        },
    }
    return report



def _background_section(item, session, evaluation, round_state) -> dict[str, Any]:
    config = dict(round_state.get("runtime_config") or {})
    if not config:
        config = {
            "runtime_mode": evaluation.get("runtime_mode", "-"),
            "llm_model_name": session.get("llm_model_name", "-"),
            "agent_dialogue_rounds": evaluation.get("agent_dialogue_rounds", "-"),
            "live_interview_enabled": evaluation.get("live_interview_enabled", "-"),
        }
    return {
        "last_known_issue": str(item.get("visible_through_period", "")).strip() or "-",
        "target_prediction_issue": str(item.get("predicted_period", "")).strip() or "-",
        "risk_visible_draw_window": str(round_state.get("issue_base", "")).strip() or f"<= {item.get('visible_through_period', '-')}",
        "runtime_config": config,
        "participants": list(round_state.get("participant_agents") or session.get("agents") or []),
    }


def _raw_signals_section(round_state) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in list(dict(round_state.get("signal_predictions") or {}).values())[:MAX_SIGNAL_LINES * 2]:
        group = str(item.get("group", "")).strip() or "-"
        grouped[group].append(
            {
                "strategy_id": str(item.get("strategy_id", "")).strip(),
                "display_name": str(item.get("display_name", "")).strip(),
                "numbers": list(item.get("numbers", [])),
                "rationale": str(item.get("rationale", "")).strip() or "-",
            }
        )
    return {key: grouped.get(key, [])[:MAX_SIGNAL_LINES] for key in GROUP_LABELS}


def _social_process_section(round_state) -> dict[str, Any]:
    social_events = list(round_state.get("social_events") or [])
    judge_events = list(round_state.get("market_ranks") or [])
    return {
        "references": _reference_lines(social_events),
        "oppositions": _opposition_lines(social_events, judge_events),
        "amplified_numbers": _amplified_number_lines(social_events),
        "crowded_structures": _crowded_structure_lines(social_events, judge_events),
    }


def _purchase_comparison_section(item, session, round_state) -> dict[str, Any]:
    final_plan = dict(round_state.get("final_plan") or {})
    final_decision = dict(round_state.get("final_decision") or {})
    numbers = list(_reference_numbers(final_plan) or dict(item.get("purchase_recommendation") or {}).get("numbers", []))
    play_size = final_plan.get("play_size") or dict(item.get("purchase_recommendation") or {}).get("play_size") or "-"
    return {
        "budget_yuan": int(session.get("budget_yuan", 0) or 0),
        "gameplay": f"快乐8选{play_size}",
        "plan_type": str(final_plan.get("plan_type") or dict(item.get("purchase_recommendation") or {}).get("plan_type") or "-"),
        "combination_structure": dict(final_plan.get("plan_structure") or {}),
        "purchase_chair_numbers": numbers,
        "official_numbers": list(item.get("official_prediction", [])),
        "accepted_by_final_decider": bool(final_decision.get("accepted_purchase_recommendation", False)),
    }


def _final_decision_section(item, round_state) -> dict[str, Any]:
    decision = dict(round_state.get("final_decision") or {})
    adopted = [str(value) for value in decision.get("adopted_groups", []) if str(value).strip()]
    return {
        "numbers": list(item.get("official_prediction", [])),
        "alternate_numbers": list(item.get("official_alternate_numbers", [])),
        "why_selected": str(decision.get("rationale", "")).strip() or "-",
        "why_not_others": _why_not_others(decision, round_state),
        "adopted_groups": adopted,
    }


def _postmortem_section(item, round_state, settlement) -> dict[str, Any]:
    purchase = dict(item.get("purchase_recommendation") or {})
    return {
        "actual_numbers": list(item.get("actual_numbers", [])),
        "official_hits": int(item.get("official_hits", 0) or 0),
        "purchase_hits": int(settlement.get("reference_leg_hits", 0) or 0),
        "group_best_hits": _group_best_hits(settlement),
        "profit_yuan": purchase.get("profit_yuan", "-"),
        "roi": purchase.get("roi", "-"),
        "payout_yuan": purchase.get("payout_yuan", "-"),
        "weight_calibration_suggestions": _weight_calibration_lines(item, round_state),
    }


def _round_state_for_period(session: dict[str, Any], period: str) -> dict[str, Any]:
    for item in reversed(list(session.get("round_history") or [])):
        if str(item.get("target_period", "")).strip() == period:
            return dict(item)
    return {}


def _settlement_for_period(session: dict[str, Any], period: str) -> dict[str, Any]:
    for item in reversed(list(session.get("settlement_history") or [])):
        if str(item.get("period", "")).strip() == period:
            return dict(item)
    return {}


def _reference_lines(events: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in events[:MAX_SOCIAL_LINES]:
        meta = dict(item.get("metadata") or {})
        refs = [*meta.get("trusted_strategy_ids", []), *meta.get("support_agent_ids", [])]
        if refs:
            lines.append(f"{_actor(item)} 引用了 {', '.join(_dedupe_strings(refs))}")
    return lines or ["无明确引用记录。"]


def _opposition_lines(social_events: list[dict[str, Any]], judge_events: list[dict[str, Any]]) -> list[str]:
    lines = [_warning_line(item) for item in [*social_events, *judge_events]]
    filtered = [item for item in lines if item]
    return filtered[:MAX_SOCIAL_LINES] or ["无明确反对记录。"]


def _amplified_number_lines(events: list[dict[str, Any]]) -> list[str]:
    counter = Counter(int(number) for item in events for number in item.get("numbers", []))
    rows = [f"{number} x {count}" for number, count in counter.most_common(MAX_SOCIAL_LINES)]
    return rows or ["无明显放大号码。"]


def _crowded_structure_lines(social_events: list[dict[str, Any]], judge_events: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in [*social_events, *judge_events]:
        meta = dict(item.get("metadata") or {})
        comment = str(item.get("content", "") or item.get("comment", "")).strip()
        structure = str(meta.get("structure_bias", "")).strip()
        if structure and _is_warning_text(comment):
            lines.append(f"{_actor(item)} 警告 `{structure}` 结构可能拥挤: {comment}")
    return lines[:MAX_SOCIAL_LINES] or ["暂无明确的拥挤结构警告。"]


def _group_best_hits(settlement: dict[str, Any]) -> list[dict[str, Any]]:
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


def _weight_calibration_lines(item: dict[str, Any], round_state: dict[str, Any]) -> list[str]:
    rows = []
    for event in list(round_state.get("postmortem_events") or [])[:MAX_REVIEW_LINES]:
        comment = str(event.get("content", "")).strip()
        if comment:
            rows.append(f"{_actor(event)}: {comment}")
    if rows:
        return rows
    summary = str(dict(item.get("latest_review") or {}).get("summary", "")).strip()
    return [summary] if summary else ["暂无校准建议。"]


def _why_not_others(decision: dict[str, Any], round_state: dict[str, Any]) -> str:
    accepted = bool(decision.get("accepted_purchase_recommendation", False))
    risk_note = str(decision.get("risk_note", "")).strip()
    if accepted:
        return risk_note or "最终方案接受了 purchase_chair 的主建议，仅保留风险备注。"
    purchase = dict(round_state.get("final_plan") or {})
    purchase_numbers = number_line(_reference_numbers(purchase))
    return risk_note or f"最终方案没有直接照搬 purchase_chair `{purchase_numbers}`，因为需要进一步控制拥挤与分散风险。"


def _reference_numbers(plan: dict[str, Any]) -> list[Any]:
    primary = list(plan.get("primary_ticket", []))
    if primary:
        return primary
    legs = list(plan.get("legs", []))
    if legs:
        return list(dict(legs[0]).get("numbers", []))
    return []


def _warning_line(item: dict[str, Any]) -> str:
    actor_id = str(item.get("actor_id", "")).strip()
    comment = str(item.get("content", "") or item.get("comment", "")).strip()
    if "risk" not in actor_id and not _is_warning_text(comment):
        return ""
    return f"{_actor(item)} 对 `{number_line(item.get('numbers', []))}` 提出了反对/警告: {comment or '-'}"


def _is_warning_text(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in WARNING_TOKENS)


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


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen = set()
    rows = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _actor(item: dict[str, Any]) -> str:
    return str(item.get("actor_display_name", "") or item.get("display_name", "") or item.get("actor_id", "-")).strip()
