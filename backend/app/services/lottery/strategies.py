"""Compatibility exports for lottery strategy agents."""

from .agents import StrategyAgent, build_data_agents, build_hybrid_agents, build_metaphysics_agents


def build_default_strategy_agents(chart_count: int = 0) -> dict[str, StrategyAgent]:
    strategies = {}
    strategies.update(build_data_agents())
    strategies.update(build_metaphysics_agents(chart_count))
    strategies.update(build_hybrid_agents())
    return strategies


__all__ = ["StrategyAgent", "build_default_strategy_agents"]
