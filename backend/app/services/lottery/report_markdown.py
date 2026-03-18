"""Markdown rendering for lottery world reports."""

from __future__ import annotations


def build_markdown_report(payload: dict[str, object]) -> str:
    dataset = dict(payload.get("dataset") or {})
    evaluation = dict(payload.get("evaluation") or {})
    session = dict(payload.get("world_session") or {})
    pending = dict(payload.get("pending_prediction") or {})
    artifacts = dict(payload.get("report_artifacts") or {})
    lines = [
        "# Lottery World Report",
        "",
        "## Artifacts",
        "",
        f"- Run ID: `{artifacts.get('run_id', '-')}`",
        f"- Saved At: `{artifacts.get('saved_at', '-')}`",
        f"- JSON: `{artifacts.get('json_path', '-')}`",
        f"- Markdown: `{artifacts.get('markdown_path', '-')}`",
        "",
        "## Dataset",
        "",
        f"- Completed Draws: `{dataset.get('completed_draws', '-')}`",
        f"- Pending Draws: `{dataset.get('pending_draws', '-')}`",
        f"- Latest Completed Period: `{dataset.get('latest_completed_period', '-')}`",
        f"- Target Period: `{dataset.get('pending_target_period', '-')}`",
        f"- Runtime Mode: `{evaluation.get('runtime_mode', '-')}`",
        f"- Visible Through Period: `{evaluation.get('visible_through_period', session.get('visible_through_period', '-'))}`",
        f"- Dialogue Rounds: `{evaluation.get('agent_dialogue_rounds', '-')}`",
        "",
        "## Session",
        "",
        f"- Session ID: `{session.get('session_id', '-')}`",
        f"- Status: `{session.get('status', '-')}`",
        f"- Current Phase: `{session.get('current_phase', '-')}`",
        f"- Current Period: `{session.get('current_period', '-')}`",
        f"- Completion Message: `{dict(session.get('progress') or {}).get('completion_message', '-')}`",
        "",
        "## Pending Prediction",
        "",
        f"- Predicted Period: `{pending.get('predicted_period', pending.get('period', '-'))}`",
        f"- Visible Through Period: `{pending.get('visible_through_period', '-')}`",
        f"- Official Numbers: `{_number_line(dict(pending.get('final_decision') or {}).get('numbers', pending.get('ensemble_numbers', [])))}`",
        f"- Official Alternates: `{_number_line(dict(pending.get('final_decision') or {}).get('alternate_numbers', pending.get('alternate_numbers', [])))}`",
        f"- Purchase Recommendation: `{_number_line(dict(pending.get('purchase_recommendation') or {}).get('primary_ticket', []))}`",
        "",
        "## Latest Review",
        "",
    ]
    lines.extend(_review_lines(dict(pending.get("latest_review") or session.get("latest_review") or {})))
    lines.extend(
        [
            "## Issue Ledger",
            "",
        ]
    )
    lines.extend(_ledger_lines(list(session.get("issue_ledger") or [])))
    return "\n".join(lines).strip() + "\n"


def _review_lines(review: dict[str, object]) -> list[str]:
    if not review:
        return ["- No review yet.", ""]
    return [
        f"- Period: `{review.get('period', '-')}`",
        f"- Official Hits: `{review.get('official_hits', '-')}`",
        f"- Purchase Profit: `{review.get('purchase_profit', '-')}`",
        f"- Purchase ROI: `{review.get('purchase_roi', '-')}`",
        f"- Summary: {review.get('summary', '-')}",
        "",
    ]


def _ledger_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- No settled issues yet.", ""]
    lines = [
        "| Period | Visible Through | Official Hits | Purchase Profit | Purchase ROI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        purchase = dict(row.get("purchase_recommendation") or {})
        lines.append(
            f"| {row.get('predicted_period', '-')} | {row.get('visible_through_period', '-')} | "
            f"{row.get('official_hits', '-')} | {purchase.get('profit_yuan', '-')} | {purchase.get('roi', '-')} |"
        )
    lines.append("")
    return lines


def _number_line(values) -> str:
    rows = [str(value) for value in values or []]
    return ", ".join(rows) or "-"
