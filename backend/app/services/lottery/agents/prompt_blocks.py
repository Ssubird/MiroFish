"""Reusable prompt blocks for LLM-backed lottery agents."""

from __future__ import annotations

from collections import Counter

from ..graph_context import DomainGraphService
from ..performance_summary import format_performance_block


RECENT_WINDOW = 18
SUMMARY_LIMIT = 10
PROMPT_LIMIT = 1
REPORT_LIMIT = 2
REPORT_EXCERPT_CHARS = 360
REPORT_SIGNAL_LIMIT = 4
REPORT_LINE_CHARS = 140
SOCIAL_HISTORY_LIMIT = 3
WORLD_ISSUE_LIMIT = 3
WORLD_POST_LIMIT = 4
WORLD_INTERVIEW_LIMIT = 3
REPORT_KEYWORDS = ("cold", "hot", "hit", "backtest", "review", "roi", "discussion", "objective", "冷号", "热号", "命中", "复盘")
REPORT_PRIORITY_KEYWORDS = ("cold", "hot", "roi", "hit distribution", "命中分布", "backtest window", "回测窗口", "objective")


def target_summary(context) -> str:
    daily = context.target_draw.daily_energy
    hourly = context.target_draw.hourly_energy
    return "\n".join(
        [
            f"Target Period: {context.target_draw.period}",
            f"Target Date: {context.target_draw.date}",
            f"Daily Energy: {daily.stem}{daily.branch} / {' '.join(daily.mutagen)}",
            f"Hourly Energy: {hourly.stem}{hourly.branch} / {' '.join(hourly.mutagen)}",
        ]
    )


def history_summary(context) -> str:
    segment = context.history_draws[-RECENT_WINDOW:]
    counter = Counter(number for draw in segment for number in draw.numbers)
    hot_numbers = [str(number) for number, _ in counter.most_common(SUMMARY_LIMIT)]
    cold_numbers = [str(number) for number in range(1, 81) if counter[number] == 0][:SUMMARY_LIMIT]
    recent_periods = ", ".join(draw.period for draw in segment[-5:]) or "-"
    return "\n".join(
        [
            f"Recent Periods: {recent_periods}",
            f"Hot Numbers in Last {RECENT_WINDOW}: {', '.join(hot_numbers) or '-'}",
            f"Cold Numbers in Last {RECENT_WINDOW}: {', '.join(cold_numbers) or '-'}",
        ]
    )


def graph_summary(context) -> str:
    return DomainGraphService().to_text(context.graph_snapshot)


def performance_summary(context) -> str:
    return format_performance_block(dict(context.strategy_performance))


def expert_interview_summary(context) -> str:
    interviews = tuple(getattr(context, "expert_interviews", ()) or ())
    if not interviews:
        return "No expert interviews yet."
    return "\n".join(_interview_line(item) for item in interviews)


def prompt_summary(context) -> str:
    prompts = [item for item in context.knowledge_documents if item.kind == "prompt"]
    if not prompts:
        return "No dedicated Happy 8 prompt asset."
    return "\n".join(f"- {item.name}: {_report_excerpt(item.content)}" for item in prompts[:PROMPT_LIMIT])


def named_report_summary(context, name: str) -> str:
    reports = [item for item in context.knowledge_documents if item.kind == "report" and item.name == name]
    if not reports:
        return f"Report not found: {name}"
    ordered = sorted(reports, key=lambda item: str(item.metadata.get("max_visible_period", item.relative_path)), reverse=True)
    return _report_line(ordered[0])


def report_summary(context) -> str:
    reports = [item for item in context.knowledge_documents if item.kind == "report"]
    if not reports:
        return "No external report is visible for this period."
    ordered = sorted(reports, key=lambda item: str(item.metadata.get("max_visible_period", item.relative_path)), reverse=True)
    return "\n".join(_report_line(report) for report in ordered[:REPORT_LIMIT])


def optimization_goal(context) -> str:
    return context.optimization_goal or "Goal: jointly optimize hit rate, ROI, stability, and anti-overheat penalty."


def single_ticket_rule(pick_size: int) -> str:
    return "\n".join(
        [
            f"Your strategy output must be exactly one final {pick_size}-number ticket.",
            "Do not output pools, wheel, dan_tuo, backup sets, or multiple candidate tickets.",
            "The system will generate 3 alternate numbers separately, and the purchase committee may expand the buy plan later.",
        ]
    )


def social_goal() -> str:
    return "Read the leaderboard, public posts, expert interviews, and external reports before deciding whether to follow, revise, or oppose peer views."


def social_memory_summary(context, strategy_id: str) -> str:
    state = dict(context.social_state).get(strategy_id)
    if not state:
        return "persona=none\ntrust_network=-\nrecent_posts=-\nrecent_revisions=-"
    trust_network = ", ".join(state.get("trust_network", [])) or "-"
    posts = _social_history(state.get("post_history"), _post_line)
    revisions = _social_history(state.get("revision_history"), _revision_line)
    return "\n".join(
        [
            f"persona={state.get('persona', '-')}",
            f"trust_network={trust_network}",
            f"recent_posts={posts}",
            f"recent_revisions={revisions}",
        ]
    )


def world_summary(context) -> str:
    state = dict(getattr(context, "world_state", {}) or {})
    if not state:
        return "No world-state memory yet."
    return "\n".join(
        [
            f"recent_issues={_world_issue_lines(state.get('issue_history'))}",
            f"trend_numbers={_world_trend_lines(state.get('trend_numbers'))}",
            f"recent_posts={_world_post_lines(state.get('public_posts'))}",
            f"recent_interviews={_world_interview_lines(state.get('interview_history'))}",
        ]
    )


def _social_history(raw: object, formatter) -> str:
    if not isinstance(raw, list) or not raw:
        return "-"
    lines = [formatter(item) for item in raw[-SOCIAL_HISTORY_LIMIT:] if isinstance(item, dict)]
    return " | ".join(lines) or "-"


def _post_line(item: dict[str, object]) -> str:
    return (
        f"{item.get('period', '-')}: numbers={item.get('numbers', [])} "
        f"hits={item.get('hits', '-')} trust={item.get('trusted_strategy_ids', [])}"
    )


def _revision_line(item: dict[str, object]) -> str:
    return f"{item.get('period', '-')}/r{item.get('round', '-')}: {item.get('numbers_before', [])}->{item.get('numbers_after', [])}"


def _interview_line(item: dict[str, object]) -> str:
    evidence = " | ".join(item.get("report_evidence", [])) or "-"
    recent = item.get("recent_hits", [])
    return "\n".join(
        [
            (
                f"- @{item.get('source_strategy_id', '-')} | {item.get('display_name', '-')} | "
                f"{item.get('group', '-')}/{item.get('kind', '-')} | "
                f"rank=#{item.get('rank', '-')}, objective={float(item.get('objective_score', 0.0)):.4f}, "
                f"avg={float(item.get('average_hits', 0.0)):.2f}, roi={float(item.get('strategy_roi', 0.0)):.2f}, "
                f"recent={recent}"
            ),
            f"  Numbers: {item.get('numbers', [])}",
            f"  Interview Answer: {item.get('answer', '')}",
            f"  Report Evidence: {evidence}",
        ]
    )


def _world_issue_lines(raw: object) -> str:
    if not isinstance(raw, list) or not raw:
        return "-"
    lines = [_world_issue_line(item) for item in raw[-WORLD_ISSUE_LIMIT:] if isinstance(item, dict)]
    return " | ".join(lines) or "-"


def _world_trend_lines(raw: object) -> str:
    if not isinstance(raw, list) or not raw:
        return "-"
    lines = [f"{item.get('number', '-')}x{item.get('mentions', 0)}" for item in raw[:SUMMARY_LIMIT] if isinstance(item, dict)]
    return ", ".join(lines) or "-"


def _world_post_lines(raw: object) -> str:
    if not isinstance(raw, list) or not raw:
        return "-"
    lines = [_world_post_line(item) for item in raw[-WORLD_POST_LIMIT:] if isinstance(item, dict)]
    return " | ".join(lines) or "-"


def _world_interview_lines(raw: object) -> str:
    if not isinstance(raw, list) or not raw:
        return "-"
    lines = [
        f"{item.get('period', '-')}/{item.get('source_strategy_id', '-')}: {item.get('numbers', [])}"
        for item in raw[-WORLD_INTERVIEW_LIMIT:]
        if isinstance(item, dict)
    ]
    return " | ".join(lines) or "-"


def _report_excerpt(content: str) -> str:
    priority = []
    fallback = []
    for line in content.splitlines():
        compact = " ".join(line.split())
        if not compact or compact.startswith(("说明:", "提示:", "|")):
            continue
        target = priority if _has_keyword(compact, REPORT_PRIORITY_KEYWORDS) else fallback
        if _has_keyword(compact, REPORT_KEYWORDS):
            target.append(compact[:REPORT_LINE_CHARS])
        if len(priority) >= REPORT_SIGNAL_LIMIT:
            break
    matches = (priority + fallback)[:REPORT_SIGNAL_LIMIT]
    if matches:
        return " | ".join(matches)
    return " ".join(content.split())[:REPORT_EXCERPT_CHARS]


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _report_line(report) -> str:
    metadata = dict(getattr(report, "metadata", {}) or {})
    window = f"{metadata.get('effective_period', '-')} < period <= {metadata.get('max_visible_period', '-')}"
    return f"- {report.name} (visible_window={window}): {_report_excerpt(report.content)}"


def _world_issue_line(item: dict[str, object]) -> str:
    actual = item.get("actual_numbers")
    if not actual:
        return f"{item.get('period', '-')}: consensus={item.get('consensus_numbers', [])}"
    return (
        f"{item.get('period', '-')}: consensus={item.get('consensus_numbers', [])}, "
        f"actual={actual}, consensus_hits={item.get('consensus_hits', 0)}, "
        f"best_hits={item.get('best_hits', 0)} by {item.get('best_strategy_ids', [])}"
    )


def _world_post_line(item: dict[str, object]) -> str:
    message = " ".join(str(item.get("message", "")).split())
    compact = message if len(message) <= 36 else message[:36].rstrip() + "..."
    return f"{item.get('period', '-')}/{item.get('strategy_id', '-')}: {item.get('numbers', [])} note={compact or '-'}"
