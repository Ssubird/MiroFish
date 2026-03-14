"""Helpers for rolling-window backtest execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .models import DrawRecord, StrategyPrediction


@dataclass(frozen=True)
class IssueTask:
    index: int
    history: tuple[DrawRecord, ...]
    target_draw: DrawRecord


def build_issue_tasks(
    completed_draws: tuple[DrawRecord, ...],
    evaluation_size: int,
) -> list[IssueTask]:
    history_cutoff = len(completed_draws) - evaluation_size
    return [
        IssueTask(
            index=offset,
            history=tuple(completed_draws[: history_cutoff + offset]),
            target_draw=target_draw,
        )
        for offset, target_draw in enumerate(completed_draws[-evaluation_size:])
    ]


def run_issue_tasks(
    tasks: list[IssueTask],
    predictor: Callable[[IssueTask], dict[str, StrategyPrediction]],
    parallelism: int,
) -> list[dict[str, StrategyPrediction]]:
    if parallelism <= 1 or len(tasks) <= 1:
        return [predictor(task) for task in tasks]
    return _parallel_issue_tasks(tasks, predictor, parallelism)


def _parallel_issue_tasks(
    tasks: list[IssueTask],
    predictor: Callable[[IssueTask], dict[str, StrategyPrediction]],
    parallelism: int,
) -> list[dict[str, StrategyPrediction]]:
    max_workers = min(parallelism, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lottery-window") as pool:
        futures = {
            task.index: pool.submit(predictor, task)
            for task in tasks
        }
        return [futures[index].result() for index in range(len(tasks))]
