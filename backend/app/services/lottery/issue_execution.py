"""Issue-level seeding and society execution helpers."""

from __future__ import annotations

from .backtest_support import coordination_trace
from .constants import JUDGE_GROUP, PRIMARY_GROUPS, SOCIAL_GROUP
from .context import attach_expert_interviews, attach_peer_predictions
from .execution import run_strategy_stage
from .runtime_helpers import by_group, grouped_strategies


def execute_issue_pipeline(
    context,
    strategies: dict[str, object],
    pick_size: int,
    options,
    dialogue_coordinator,
    include_trace: bool = False,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    primary_initial = run_strategy_stage(context, grouped_strategies(strategies, PRIMARY_GROUPS), pick_size, options.parallelism)
    social_context = _interview_context(context, primary_initial)
    social_initial = _seed_social(social_context, strategies, pick_size, options.parallelism)
    judge_context = _interview_context(context, {**primary_initial, **social_initial})
    judge_initial = _seed_judges(judge_context, strategies, pick_size, options.parallelism)
    seeded_predictions = {**primary_initial, **social_initial, **judge_initial}
    society_context = _interview_context(context, seeded_predictions)
    society = _run_society(society_context, strategies, seeded_predictions, pick_size, options, dialogue_coordinator)
    if not include_trace:
        return society.predictions, []
    trace = coordination_trace(
        [
            ("primary_seed", "主策略初始出号", primary_initial),
            ("social_seed", "社交组首轮发帖", social_initial),
            ("judge_seed", "裁判组首轮裁决", judge_initial),
        ],
        society.rounds,
        society.predictions,
    )
    return society.predictions, trace


def _seed_social(
    context,
    strategies: dict[str, object],
    pick_size: int,
    parallelism: int,
) -> dict[str, object]:
    social = by_group(strategies, SOCIAL_GROUP)
    if not social or not context.peer_predictions:
        return {}
    return run_strategy_stage(context, social, pick_size, parallelism)


def _seed_judges(
    context,
    strategies: dict[str, object],
    pick_size: int,
    parallelism: int,
) -> dict[str, object]:
    judges = by_group(strategies, JUDGE_GROUP)
    if not judges or not context.peer_predictions:
        return {}
    return run_strategy_stage(context, judges, pick_size, parallelism)


def _interview_context(context, predictions: dict[str, object]):
    seeded = attach_peer_predictions(context, predictions)
    return attach_expert_interviews(seeded, predictions)


def _run_society(
    context,
    strategies: dict[str, object],
    predictions: dict[str, object],
    pick_size: int,
    options,
    dialogue_coordinator,
):
    if not options.agent_dialogue_enabled or not predictions:
        return dialogue_coordinator.run(context, {}, predictions, pick_size, 0, options.parallelism)
    return dialogue_coordinator.run_society(
        context,
        strategies,
        predictions,
        pick_size,
        options.agent_dialogue_rounds,
        options.parallelism,
    )
