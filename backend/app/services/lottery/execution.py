"""Helpers for safe per-stage concurrent strategy execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .agents import StrategyAgent
from .models import PredictionContext, StrategyPrediction


def run_strategy_stage(
    context: PredictionContext,
    strategies: dict[str, StrategyAgent],
    pick_size: int,
    parallelism: int,
) -> dict[str, StrategyPrediction]:
    if parallelism <= 1 or len(strategies) <= 1:
        return _sequential_stage(context, strategies, pick_size)
    return _parallel_stage(context, strategies, pick_size, parallelism)


def _sequential_stage(
    context: PredictionContext,
    strategies: dict[str, StrategyAgent],
    pick_size: int,
) -> dict[str, StrategyPrediction]:
    return {
        strategy_id: strategy.predict(context, pick_size)
        for strategy_id, strategy in strategies.items()
    }


def _parallel_stage(
    context: PredictionContext,
    strategies: dict[str, StrategyAgent],
    pick_size: int,
    parallelism: int,
) -> dict[str, StrategyPrediction]:
    max_workers = min(parallelism, len(strategies))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lottery-stage") as pool:
        futures = {
            strategy_id: pool.submit(strategy.predict, context, pick_size)
            for strategy_id, strategy in strategies.items()
        }
        return {
            strategy_id: futures[strategy_id].result()
            for strategy_id in strategies
        }
