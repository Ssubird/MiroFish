"""Markdown rendering for detailed lottery reports."""

from __future__ import annotations

from .report_markdown_support import (
    coordination_section,
    judge_section,
    live_interviews_section,
    metadata_lines,
    number_line,
    purchase_section,
    social_state_section,
    world_timeline_section,
    world_state_section,
)


def build_markdown_report(payload: dict[str, object]) -> str:
    sections = [
        ["# Lottery World Report", ""],
        artifact_section(payload),
        dataset_section(payload.get("dataset") or {}, payload.get("evaluation") or {}),
        session_snapshot_section(payload.get("world_session") or {}),
        asset_manifest_section(payload.get("world_session", {}) or {}),
        file_usage_section(payload.get("world_session", {}) or {}),
        process_section(payload.get("process_trace") or []),
        leaderboard_section(payload.get("leaderboard") or []),
        pending_section(payload.get("pending_prediction") or {}),
    ]
    lines: list[str] = []
    for section in sections:
        lines.extend(section)
    return "\n".join(lines).strip() + "\n"


def artifact_section(payload: dict[str, object]) -> list[str]:
    artifacts = payload.get("report_artifacts") or {}
    return [
        f"- Run ID: `{artifacts.get('run_id', '-')}`",
        f"- Saved At: `{artifacts.get('saved_at', '-')}`",
        f"- JSON: `{artifacts.get('json_path', '-')}`",
        f"- Markdown: `{artifacts.get('markdown_path', '-')}`",
        "",
    ]


def dataset_section(dataset: dict[str, object], evaluation: dict[str, object]) -> list[str]:
    policy = evaluation.get("objective_policy") or {}
    weights = policy.get("weights") or {}
    return [
        "## Dataset",
        "",
        f"- Completed Draws: `{dataset.get('completed_draws', '-')}`",
        f"- Pending Draws: `{dataset.get('pending_draws', '-')}`",
        f"- Latest Completed Period: `{dataset.get('latest_completed_period', '-')}`",
        f"- Target Period: `{dataset.get('pending_target_period', '-')}`",
        f"- Scored Window: `{evaluation.get('evaluation_size', '-')}`",
        f"- Warmup Window: `{evaluation.get('warmup_size', '-')}`",
        f"- Pick Size: `{evaluation.get('pick_size', '-')}`",
        f"- Runtime Mode: `{evaluation.get('runtime_mode', 'legacy')}`",
        f"- Graph Mode: `{evaluation.get('graph_mode', '-')}`",
        f"- LLM Model: `{evaluation.get('llm_model_name', '-')}`",
        f"- Live Interview Enabled: `{evaluation.get('live_interview_enabled', '-')}`",
        (
            f"- Parallelism: `llm_parallelism={evaluation.get('llm_parallelism', '-')}` / "
            f"`issue_parallelism={evaluation.get('issue_parallelism', '-')}`"
        ),
        (
            f"- Dialogue: `enabled={evaluation.get('agent_dialogue_enabled', '-')}` / "
            f"`rounds={evaluation.get('agent_dialogue_rounds', '-')}`"
        ),
        (
            f"- Objective: `{policy.get('sort_key', '-')}` / "
            f"hit={weights.get('hit_rate', '-')} / roi={weights.get('roi', '-')} / "
            f"stability={weights.get('stability_penalty', '-')} / heat={weights.get('heat_penalty', '-')}"
        ),
        f"- World Mode: `{evaluation.get('world_mode', '-')}`",
        "",
    ]


def asset_manifest_section(world_session: dict[str, object]) -> list[str]:
    rows = world_session.get("asset_manifest") or []
    if not rows:
        return []
    lines = ["## Asset Manifest", "", "| Name | Role | Active | Path | Note |", "| --- | --- | --- | --- | --- |"]
    for item in rows:
        lines.append(
            f"| {item.get('name', '-')} | {item.get('role', '-')} | {item.get('active', '-')} | "
            f"{item.get('path', '-')} | {item.get('note', '-')} |"
        )
    lines.append("")
    return lines


def session_snapshot_section(world_session: dict[str, object]) -> list[str]:
    if not world_session:
        return []
    return [
        "## Session Snapshot",
        "",
        f"- Session ID: `{world_session.get('session_id', '-')}`",
        f"- Status: `{world_session.get('status', '-')}`",
        f"- Current Phase: `{world_session.get('current_phase', '-')}`",
        f"- Current Period: `{world_session.get('current_period', '-')}`",
        f"- Last Success Phase: `{world_session.get('last_success_phase', '-')}`",
        f"- Failed Phase: `{world_session.get('failed_phase', '-')}`",
        f"- Active Agents: `{', '.join(world_session.get('active_agent_ids', [])) or '-'}`",
        "",
    ]


def file_usage_section(world_session: dict[str, object]) -> list[str]:
    manual = world_session.get("manual_reference_documents") or []
    lines = [
        "## File Usage Policy",
        "",
        "- `keno8_predict_data.json` 是唯一权威数据源，会进入运行时并决定当前目标期。",
        "- `prompt.md` 是当前有效提示资产，会进入 agent 的主动上下文和 Letta 记忆。",
        "- `prediction_report.md` 仅作人工参考，不会进入 runtime、grounding、agent 或购买委员会。",
    ]
    if manual:
        lines.append("")
        lines.append("### Manual References")
        lines.append("")
        for item in manual:
            lines.append(f"- `{item.get('name', '-')}` / `{item.get('path', '-')}`: {item.get('note', '-')}")
    lines.append("")
    return lines


def process_section(trace: list[dict[str, object]]) -> list[str]:
    lines = ["## Process", "", "| Step | Status | Details |", "| --- | --- | --- |"]
    for item in trace:
        lines.append(f"| {item.get('title', '-')} | {item.get('status', '-')} | {item.get('details', '-')} |")
        preview = item.get("preview_periods") or []
        if preview:
            lines.append(f"- Preview Periods: `{', '.join(preview)}`")
        highlights = item.get("highlights") or []
        if highlights:
            lines.append(f"- Graph Highlights: `{', '.join(highlights)}`")
        if item.get("leader"):
            lines.append(f"- Leader: `{item['leader']}`")
    return [*lines, ""]


def leaderboard_section(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "## Leaderboard",
        "",
        "| Rank | Agent | Group | Kind | Objective | Avg Hits | ROI | Stddev | Recent |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(rows, start=1):
        recent = ",".join(str(item["hits"]) for item in row.get("issue_hits", [])[-5:]) or "-"
        lines.append(
            f"| {index} | {row['display_name']} | {row['group']} | {row['kind']} | "
            f"{float(row.get('objective_score', 0.0)):.4f} | {row.get('average_hits', '-')} | "
            f"{float(row.get('strategy_roi', 0.0)):.4f} | {row.get('hit_stddev', '-')} | {recent} |"
        )
    lines.append("")
    for index, row in enumerate(rows, start=1):
        lines.extend(leader_detail(index, row))
    return lines


def leader_detail(index: int, row: dict[str, object]) -> list[str]:
    lines = [
        f"### #{index} {row['display_name']}",
        "",
        f"- Strategy ID: `{row['strategy_id']}`",
        f"- Group / Kind: `{row['group']} / {row['kind']}`",
        (
            f"- Objective: `{float(row.get('objective_score', 0.0)):.4f}` / "
            f"Avg Hits: `{row.get('average_hits', '-')}` / "
            f"ROI: `{float(row.get('strategy_roi', 0.0)):.4f}` / "
            f"Stddev: `{row.get('hit_stddev', '-')}` / "
            f"Total Hits: `{row.get('total_hits', '-')}`"
        ),
        f"- Description: {row.get('description', '-')}",
    ]
    latest = row.get("latest_prediction")
    if latest:
        lines.append(f"- Latest Pending Numbers: `{number_line(latest.get('numbers', []))}`")
        lines.append(f"- Latest Rationale: {latest.get('rationale', '-')}")
    return [*lines, ""]


def pending_section(pending: dict[str, object]) -> list[str]:
    if not pending:
        return ["## Pending Prediction", "", "- No pending target draw.", ""]
    lines = [
        "## Pending Prediction",
        "",
        f"- Period: `{pending.get('period', '-')}`",
        f"- Date: `{pending.get('date', '-')}`",
        f"- Ensemble Numbers: `{number_line(pending.get('ensemble_numbers', []))}`",
        f"- Alternate 3 Numbers: `{number_line(pending.get('alternate_numbers', []))}`",
        "",
        "### Ensemble Breakdown",
        "",
    ]
    lines.extend(ensemble_rows(pending.get("ensemble_breakdown") or []))
    lines.extend(performance_section(pending.get("performance_context") or []))
    lines.extend(prediction_section(pending.get("strategy_predictions") or []))
    lines.extend(coordination_section(pending.get("coordination_trace") or []))
    lines.extend(judge_section(pending.get("judge_decision") or {}))
    lines.extend(live_interviews_section(pending.get("live_interviews") or []))
    lines.extend(social_state_section(pending.get("social_state") or {}))
    lines.extend(world_state_section(pending.get("world_state") or {}))
    lines.extend(world_timeline_section(pending.get("world_timeline_preview") or []))
    lines.extend(purchase_section(pending.get("purchase_plan") or {}))
    return lines


def ensemble_rows(rows: list[dict[str, object]]) -> list[str]:
    lines = ["| Number | Score | Sources |", "| --- | --- | --- |"]
    for item in rows:
        lines.append(f"| {item['number']} | {item['score']} | {', '.join(item.get('sources', [])) or '-'} |")
    return [*lines, ""]


def performance_section(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return []
    lines = [
        "### Performance Context",
        "",
        "| Rank | Agent | Objective | Avg | ROI | Stddev | Recent |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        recent = ",".join(str(value) for value in item.get("recent_hits", [])) or "-"
        lines.append(
            f"| {item['rank']} | {item['display_name']} (`{item['strategy_id']}`) | "
            f"{float(item.get('objective_score', 0.0)):.4f} | {float(item.get('average_hits', 0.0)):.4f} | "
            f"{float(item.get('strategy_roi', 0.0)):.4f} | {float(item.get('hit_stddev', 0.0)):.4f} | {recent} |"
        )
    return [*lines, ""]


def prediction_section(rows: list[dict[str, object]]) -> list[str]:
    lines = ["### Agent Predictions", ""]
    for item in rows:
        lines.extend(prediction_lines(item))
    return lines


def prediction_lines(item: dict[str, object]) -> list[str]:
    lines = [
        f"#### {item['display_name']} (`{item['strategy_id']}`)",
        "",
        f"- Group / Kind: `{item['group']} / {item['kind']}`",
        (
            f"- Backtest Objective: `{float(item.get('backtest_objective_score', 0.0)):.4f}` / "
            f"Avg Hits: `{item.get('backtest_average_hits', '-')}` / "
            f"ROI: `{float(item.get('backtest_strategy_roi', 0.0)):.4f}`"
        ),
        f"- Numbers: `{number_line(item.get('numbers', []))}`",
        f"- Rationale: {item.get('rationale', '-')}",
    ]
    lines.extend(metadata_lines(item.get("metadata") or {}))
    lines.append("")
    return lines
