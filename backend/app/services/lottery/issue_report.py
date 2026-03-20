"""Per-issue report payload builders."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .issue_report_support import (
    amplified_number_lines,
    crowded_structure_lines,
    group_best_hits,
    opposition_lines,
    reference_lines,
    reference_numbers,
    top_board_numbers,
    weight_calibration_lines,
    why_not_others,
)


GROUP_LABELS = {
    "data": "数据组信号摘要",
    "metaphysics": "玄学组信号摘要",
    "hybrid": "混合组信号摘要",
}
MAX_SIGNAL_LINES = 6


def issue_report_stem(period: str) -> str:
    text = str(period).strip()
    suffix = text[-3:] if len(text) >= 3 else text.zfill(3)
    return f"issue_{suffix}_report"


def pending_issue_report_item(
    payload: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any] | None:
    pending = dict(payload.get("pending_prediction") or {})
    if not pending:
        pending = dict(session.get("latest_prediction") or {})
    period = str(pending.get("predicted_period") or pending.get("period") or "").strip()
    if not period:
        return None
    return pending


def build_issue_report_payload(
    item: dict[str, Any],
    session: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_issue_item(item)
    period = normalized["predicted_period"]
    round_state = _round_state_for_period(session, period)
    settlement = _settlement_for_period(session, period)
    report_name = issue_report_stem(period)
    return {
        "report_name": report_name,
        "issue_suffix": report_name.split("_")[1],
        "predicted_period": period,
        "visible_through_period": normalized["visible_through_period"],
        "sections": {
            "background": _background_section(normalized, session, evaluation, round_state),
            "raw_signals": _raw_signals_section(round_state),
            "social_process": _social_process_section(round_state),
            "purchase_comparison": _purchase_comparison_section(normalized, session, round_state),
            "final_decision": _final_decision_section(normalized, round_state),
            "postmortem": _postmortem_section(normalized, round_state, settlement),
        },
    }


def _normalize_issue_item(item: dict[str, Any]) -> dict[str, Any]:
    final_decision = dict(item.get("final_decision") or {})
    purchase = dict(item.get("purchase_recommendation") or item.get("purchase_plan") or {})
    period = str(item.get("predicted_period") or item.get("period") or final_decision.get("period") or "").strip()
    review = dict(item.get("latest_review") or {})
    if str(review.get("period", "")).strip() != period:
        review = {}
    actual_numbers = list(item.get("actual_numbers") or [])
    return {
        "predicted_period": period,
        "visible_through_period": str(item.get("visible_through_period", "")).strip(),
        "official_prediction": list(item.get("official_prediction") or final_decision.get("numbers") or []),
        "official_alternate_numbers": list(
            item.get("official_alternate_numbers") or final_decision.get("alternate_numbers") or []
        ),
        "purchase_recommendation": purchase,
        "actual_numbers": actual_numbers,
        "official_hits": item.get("official_hits", "-" if not actual_numbers else 0),
        "latest_review": review,
        "final_decision": final_decision,
        "pending": not actual_numbers,
    }


def _background_section(
    item: dict[str, Any],
    session: dict[str, Any],
    evaluation: dict[str, Any],
    round_state: dict[str, Any],
) -> dict[str, Any]:
    config = dict(round_state.get("runtime_config") or {})
    if not config:
        config = {
            "runtime_mode": evaluation.get("runtime_mode", "-"),
            "llm_model_name": session.get("llm_model_name", "-"),
            "agent_dialogue_rounds": evaluation.get("agent_dialogue_rounds", "-"),
            "live_interview_enabled": evaluation.get("live_interview_enabled", "-"),
        }
    return {
        "last_known_issue": item["visible_through_period"] or "-",
        "target_prediction_issue": item["predicted_period"] or "-",
        "game_id": str(session.get("game_id", "happy8")).strip() or "happy8",
        "risk_visible_draw_window": f"<= {item['visible_through_period'] or '-'} (predict {item['predicted_period'] or '-'})",
        "runtime_config": config,
        "execution_overrides": dict(session.get("execution_overrides", {})),
        "resolved_execution_bindings": dict(session.get("resolved_execution_bindings", {})),
        "participants": list(round_state.get("participant_agents") or session.get("agents") or []),
    }


def _raw_signals_section(round_state: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    signal_boards = list(round_state.get("signal_boards") or [])
    if not signal_boards:
        return {key: [] for key in GROUP_LABELS}
    for item in signal_boards[: MAX_SIGNAL_LINES * 2]:
        metadata = dict(item.get("metadata") or {})
        group = str(metadata.get("group", item.get("board_type", ""))).strip() or "-"
        grouped[group].append(
                {
                    "strategy_id": str(item.get("strategy_id", "")).strip(),
                    "display_name": str(metadata.get("display_name", item.get("strategy_id", ""))).strip(),
                    "numbers": top_board_numbers(item),
                    "rationale": str(item.get("rationale", "")).strip() or "-",
                }
            )
    return {key: grouped.get(key, [])[:MAX_SIGNAL_LINES] for key in GROUP_LABELS}


def _social_process_section(round_state: dict[str, Any]) -> dict[str, Any]:
    social_events = list(round_state.get("social_events") or [])
    judge_events = list(round_state.get("market_ranks") or [])
    return {
        "references": reference_lines(social_events),
        "oppositions": opposition_lines(social_events, judge_events),
        "amplified_numbers": amplified_number_lines(social_events),
        "crowded_structures": crowded_structure_lines(social_events, judge_events),
    }


def _purchase_comparison_section(
    item: dict[str, Any],
    session: dict[str, Any],
    round_state: dict[str, Any],
) -> dict[str, Any]:
    final_plan = dict(round_state.get("final_plan") or item.get("purchase_recommendation") or {})
    final_decision = dict(round_state.get("final_decision") or item.get("final_decision") or {})
    play_size = final_plan.get("play_size") or "-"
    return {
        "budget_yuan": int(session.get("budget_yuan", 0) or 0),
        "gameplay": f"{session.get('game_id', 'happy8')} / play_size={play_size}",
        "plan_type": str(final_plan.get("plan_type") or "-"),
        "combination_structure": dict(final_plan.get("plan_structure") or {}),
        "purchase_chair_numbers": list(reference_numbers(final_plan)),
        "official_numbers": list(item.get("official_prediction") or []),
        "accepted_by_final_decider": bool(final_decision.get("accepted_purchase_recommendation", False)),
    }


def _final_decision_section(item: dict[str, Any], round_state: dict[str, Any]) -> dict[str, Any]:
    decision = dict(round_state.get("final_decision") or item.get("final_decision") or {})
    adopted = [str(value) for value in decision.get("adopted_groups", []) if str(value).strip()]
    return {
        "numbers": list(item.get("official_prediction") or []),
        "alternate_numbers": list(item.get("official_alternate_numbers") or []),
        "why_selected": str(decision.get("rationale", "")).strip() or "-",
        "why_not_others": why_not_others(decision, round_state),
        "adopted_groups": adopted,
    }


def _postmortem_section(
    item: dict[str, Any],
    round_state: dict[str, Any],
    settlement: dict[str, Any],
) -> dict[str, Any]:
    if item.get("pending"):
        return {
            "pending": True,
            "actual_numbers": [],
            "official_hits": "-",
            "purchase_hits": "-",
            "group_best_hits": [],
            "profit_yuan": "-",
            "roi": "-",
            "payout_yuan": "-",
            "weight_calibration_suggestions": ["尚未开奖，暂无复盘。"],
        }
    purchase = dict(item.get("purchase_recommendation") or {})
    return {
        "pending": False,
        "actual_numbers": list(item.get("actual_numbers") or []),
        "official_hits": item.get("official_hits", 0),
        "purchase_hits": int(settlement.get("reference_leg_hits", 0) or 0),
        "group_best_hits": group_best_hits(settlement),
        "profit_yuan": purchase.get("profit_yuan", "-"),
        "roi": purchase.get("roi", "-"),
        "payout_yuan": purchase.get("payout_yuan", "-"),
        "weight_calibration_suggestions": weight_calibration_lines(item, round_state),
    }


def _round_state_for_period(session: dict[str, Any], period: str) -> dict[str, Any]:
    current = dict(session.get("current_round") or {})
    if str(current.get("target_period", "")).strip() == period:
        return current
    for item in reversed(list(session.get("round_history") or [])):
        if str(item.get("target_period", "")).strip() == period:
            return dict(item)
    return {}


def _settlement_for_period(session: dict[str, Any], period: str) -> dict[str, Any]:
    for item in reversed(list(session.get("settlement_history") or [])):
        if str(item.get("period", "")).strip() == period:
            return dict(item)
    return {}
