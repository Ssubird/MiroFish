"""Prompt helpers for the interactive world analyst agent."""

from __future__ import annotations

from typing import Any


ANALYST_DESCRIPTION = (
    "Explain the current lottery world, summarize agent disagreement, inspect recent draw stats, "
    "and answer interactive questions without proposing the final ticket yourself."
)


def analyst_prompt(
    session: dict[str, Any],
    user_prompt: str,
    recent_stats: dict[str, Any],
    graph_snapshot: dict[str, Any] | None,
) -> str:
    sections = [
        _session_summary(session),
        _prediction_summary(session),
        _settlement_summary(session),
        _recent_stats_summary(recent_stats),
        _graph_summary(graph_snapshot),
        f"User question:\n{user_prompt.strip()}",
        "Answer as the world analyst. Be specific, cite the world state, and do not invent missing draw results.",
    ]
    return "\n\n".join(part for part in sections if part)


def _session_summary(session: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Session: {session['session_id']}",
            f"Status: {session.get('status', '-')}",
            f"Current phase: {session.get('current_phase', '-')}",
            f"Current period: {session.get('current_period', '-')}",
            f"Budget: {session.get('budget_yuan', '-')}",
        ]
    )


def _prediction_summary(session: dict[str, Any]) -> str:
    latest = dict(session.get("latest_prediction", {}))
    if not latest:
        return "No active pending prediction yet."
    return "\n".join(
        [
            f"Latest prediction period: {latest.get('period', '-')}",
            f"Primary numbers: {latest.get('ensemble_numbers', [])}",
            f"Alternate numbers: {latest.get('alternate_numbers', [])}",
            f"Purchase plan: {dict(session.get('latest_purchase_plan', {})).get('plan_type', '-')}",
        ]
    )


def _settlement_summary(session: dict[str, Any]) -> str:
    rows = list(session.get("settlement_history", []))
    if not rows:
        return "No settled rounds yet."
    latest = rows[-1]
    return "\n".join(
        [
            f"Latest settlement period: {latest.get('period', '-')}",
            f"Actual numbers: {latest.get('actual_numbers', [])}",
            f"Consensus hits: {latest.get('consensus_hits', '-')}",
            f"Best strategy ids: {latest.get('best_strategy_ids', [])}",
        ]
    )


def _recent_stats_summary(recent_stats: dict[str, Any]) -> str:
    hot = ", ".join(str(item) for item in recent_stats.get("hot_numbers", [])[:8]) or "-"
    cold = ", ".join(str(item) for item in recent_stats.get("cold_numbers", [])[:8]) or "-"
    return "\n".join(
        [
            f"Recent draw window: {recent_stats.get('window_size', 0)}",
            f"Window range: {recent_stats.get('from_period', '-')} -> {recent_stats.get('to_period', '-')}",
            f"Hot numbers: {hot}",
            f"Cold numbers: {cold}",
        ]
    )


def _graph_summary(graph_snapshot: dict[str, Any] | None) -> str:
    if not graph_snapshot:
        return ""
    highlights = ", ".join(graph_snapshot.get("highlights", [])[:8]) or "-"
    relations = "; ".join(graph_snapshot.get("preview_relations", [])[:4]) or "-"
    return "\n".join(
        [
            f"Graph provider: {graph_snapshot.get('provider', '-')}",
            f"Graph highlights: {highlights}",
            f"Graph relations: {relations}",
        ]
    )

