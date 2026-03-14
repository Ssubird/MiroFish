"""Validation and strategy selection helpers for lottery backtests."""

from __future__ import annotations

from .constants import (
    GRAPH_MODES,
    MAX_AGENT_DIALOGUE_ROUNDS,
    MAX_LLM_REQUEST_DELAY_MS,
    MAX_LLM_RETRY_BACKOFF_MS,
    MAX_LLM_RETRY_COUNT,
    MAX_PICK_SIZE,
)


def select_strategies(
    strategies: dict[str, object],
    strategy_ids: list[str] | None,
) -> dict[str, object]:
    if not strategy_ids:
        defaults = {key: value for key, value in strategies.items() if value.default_enabled}
        return defaults or strategies
    unknown_ids = [strategy_id for strategy_id in strategy_ids if strategy_id not in strategies]
    if unknown_ids:
        raise ValueError(f"Unknown strategies: {', '.join(unknown_ids)}")
    return {strategy_id: strategies[strategy_id] for strategy_id in strategy_ids}


def primary_strategies(
    strategies: dict[str, object],
    groups: tuple[str, ...],
) -> dict[str, object]:
    return {key: value for key, value in strategies.items() if value.group in groups}


def judge_strategies(
    strategies: dict[str, object],
    judge_group: str,
) -> dict[str, object]:
    return {key: value for key, value in strategies.items() if value.group == judge_group}


def validate_request(
    evaluation_size: int,
    pick_size: int,
    delay: int,
    retry_count: int,
    retry_backoff: int,
    parallelism: int,
    issue_parallelism: int,
    dialogue_rounds: int,
    graph_mode: str,
) -> None:
    if evaluation_size <= 0:
        raise ValueError("evaluation_size must be greater than 0")
    if pick_size <= 0 or pick_size > MAX_PICK_SIZE:
        raise ValueError(f"pick_size must be between 1 and {MAX_PICK_SIZE}")
    if delay < 0 or delay > MAX_LLM_REQUEST_DELAY_MS:
        raise ValueError(f"llm_request_delay_ms must be between 0 and {MAX_LLM_REQUEST_DELAY_MS}")
    if retry_count < 0 or retry_count > MAX_LLM_RETRY_COUNT:
        raise ValueError(f"llm_retry_count must be between 0 and {MAX_LLM_RETRY_COUNT}")
    if retry_backoff < 0 or retry_backoff > MAX_LLM_RETRY_BACKOFF_MS:
        raise ValueError(f"llm_retry_backoff_ms must be between 0 and {MAX_LLM_RETRY_BACKOFF_MS}")
    if parallelism <= 0:
        raise ValueError("llm_parallelism must be greater than 0")
    if issue_parallelism <= 0:
        raise ValueError("issue_parallelism must be greater than 0")
    if dialogue_rounds < 0 or dialogue_rounds > MAX_AGENT_DIALOGUE_ROUNDS:
        raise ValueError(f"agent_dialogue_rounds must be between 0 and {MAX_AGENT_DIALOGUE_ROUNDS}")
    if graph_mode not in GRAPH_MODES:
        raise ValueError(f"graph_mode must be one of: {', '.join(GRAPH_MODES)}")


def validate_dataset(
    assets,
    evaluation_size: int,
    warmup_size: int,
    strategies: dict[str, object],
    primary: dict[str, object],
    judge: dict[str, object],
) -> None:
    if len(assets.pending_draws) > 1:
        raise ValueError("Only one pending target draw is supported")
    total_window = evaluation_size + warmup_size
    if len(assets.completed_draws) <= total_window:
        raise ValueError("Not enough completed draws for rolling backtest")
    minimum_history = max(strategy.required_history for strategy in strategies.values())
    available_history = len(assets.completed_draws) - total_window
    if available_history < minimum_history:
        required_total = minimum_history + total_window
        raise ValueError(f"Backtest needs at least {required_total} completed draws")
    if judge and not primary:
        raise ValueError("Judge strategies require at least one primary strategy")
