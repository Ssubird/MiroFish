"""Strategy catalog assembly for lottery research."""

from __future__ import annotations

from collections import Counter

from ...config import Config
from .agents import (
    build_data_agents,
    build_hybrid_agents,
    build_judge_agents,
    build_metaphysics_agents,
    build_social_agents,
)
from .constants import (
    DEFAULT_AGENT_DIALOGUE_ENABLED,
    DEFAULT_AGENT_DIALOGUE_ROUNDS,
    DEFAULT_ISSUE_PARALLELISM,
    DEFAULT_LLM_PARALLELISM,
    DEFAULT_LLM_RETRY_BACKOFF_MS,
    DEFAULT_LLM_RETRY_COUNT,
)
from .market_diversity import MARKET_V2_JUDGE_IDS


def build_strategy_catalog(chart_count: int = 0) -> dict[str, object]:
    strategies = {}
    strategies.update(build_data_agents())
    strategies.update(build_metaphysics_agents(chart_count))
    strategies.update(build_hybrid_agents())
    return strategies


def build_market_v2_catalog(chart_count: int = 0) -> dict[str, object]:
    """Catalog for World V2 Market: generators + social + selected judges."""
    strategies = build_strategy_catalog(chart_count)
    strategies.update(build_social_agents())
    judge_agents = build_judge_agents()
    for strategy_id in MARKET_V2_JUDGE_IDS:
        strategy = judge_agents.get(strategy_id)
        if strategy is not None:
            strategies[strategy_id] = strategy
    return strategies


def build_strategy_group_summary(strategies: dict[str, object]) -> dict[str, dict[str, int]]:
    grouped = Counter(getattr(strategy, "group", "unknown") for strategy in strategies.values())
    llm_grouped = Counter(
        getattr(strategy, "group", "unknown")
        for strategy in strategies.values()
        if bool(getattr(strategy, "uses_llm", False))
    )
    return {
        group: {"count": grouped[group], "llm_count": llm_grouped[group]}
        for group in sorted(grouped)
    }


def build_llm_status() -> dict[str, object]:
    return {
        "configured": bool(Config.LLM_API_KEY),
        "model": Config.LLM_MODEL_NAME,
        "base_url": Config.LLM_BASE_URL,
        "default_retry_count": DEFAULT_LLM_RETRY_COUNT,
        "default_retry_backoff_ms": DEFAULT_LLM_RETRY_BACKOFF_MS,
        "default_parallelism": DEFAULT_LLM_PARALLELISM,
        "default_issue_parallelism": DEFAULT_ISSUE_PARALLELISM,
        "default_agent_dialogue_enabled": DEFAULT_AGENT_DIALOGUE_ENABLED,
        "default_agent_dialogue_rounds": DEFAULT_AGENT_DIALOGUE_ROUNDS,
        "note": (
            "Persistent world exposes generator boards by default: data, "
            "metaphysics_fused_board, and hybrid_fused_board. Social, judge, "
            "purchase_chair, and handbook_decider participate inside world_v2_market."
        ),
    }
