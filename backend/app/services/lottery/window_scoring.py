"""Rolling-window scoring helpers."""

from __future__ import annotations

from typing import Callable

from .backtest_support import score_issue
from .performance_summary import rolling_strategy_performance
from .research_types import IssueReplay, WindowBacktest
from .window_execution import build_issue_tasks, run_issue_tasks


ADAPTIVE_PARALLELISM_ERROR = (
    "issue_parallelism 必须为 1：当前滚动回测会把上一期命中结果、"
    "历史绩效和社交状态继续传给下一期，因此验证期之间存在严格因果顺序。"
    "能并发的只有同一期内的 agent 求解，请调高 llm_parallelism。"
)


def score_issue_window(
    completed_draws,
    evaluation_size: int,
    strategies: dict[str, object],
    predictor: Callable[[object, dict[str, dict[str, object]] | None], dict[str, object]],
    issue_parallelism: int,
    adaptive: bool,
    warmup_size: int = 0,
) -> WindowBacktest:
    issue_results = {strategy_id: [] for strategy_id in strategies}
    total_window = evaluation_size + warmup_size
    tasks = build_issue_tasks(completed_draws, total_window)
    if adaptive:
        _validate_adaptive_parallelism(issue_parallelism)
        full_window = _score_adaptive_window(tasks, strategies, issue_results, predictor)
        return _trim_warmup(full_window, warmup_size)
    predictions = run_issue_tasks(tasks, lambda task: predictor(task, None), issue_parallelism)
    full_window = _assemble_window(tasks, predictions, issue_results)
    return _trim_warmup(full_window, warmup_size)


def adaptive_window_required(
    strategies: dict[str, object],
    dialogue_enabled: bool,
) -> bool:
    return dialogue_enabled or any(getattr(strategy, "uses_llm", False) for strategy in strategies.values())


def _score_adaptive_window(
    tasks,
    strategies: dict[str, object],
    issue_results: dict[str, list[dict[str, object]]],
    predictor: Callable[[object, dict[str, dict[str, object]]], dict[str, object]],
) -> WindowBacktest:
    replays = []
    for task in tasks:
        performance = rolling_strategy_performance(issue_results, strategies, task.index)
        predictions = predictor(task, performance)
        _append_issue_scores(issue_results, task.target_draw, predictions)
        replays.append(IssueReplay(task.target_draw, predictions))
    return WindowBacktest(issue_results, tuple(replays))


def _assemble_window(tasks, predictions, issue_results) -> WindowBacktest:
    replays = []
    for task, issue_prediction in zip(tasks, predictions):
        _append_issue_scores(issue_results, task.target_draw, issue_prediction)
        replays.append(IssueReplay(task.target_draw, issue_prediction))
    return WindowBacktest(issue_results, tuple(replays))


def _trim_warmup(window: WindowBacktest, warmup_size: int) -> WindowBacktest:
    if warmup_size <= 0:
        return window
    trimmed_results = {strategy_id: rows[warmup_size:] for strategy_id, rows in window.issue_results.items()}
    return WindowBacktest(
        trimmed_results,
        window.issue_replays[warmup_size:],
        window.issue_replays[:warmup_size],
        warmup_size,
        window.social_state,
        window.world_state,
    )


def _append_issue_scores(issue_results, target_draw, predictions) -> None:
    for strategy_id, prediction in predictions.items():
        issue_results[strategy_id].append(score_issue(target_draw, prediction))


def _validate_adaptive_parallelism(issue_parallelism: int) -> None:
    if issue_parallelism == 1:
        return
    raise ValueError(ADAPTIVE_PARALLELISM_ERROR)
