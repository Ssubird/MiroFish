"""Persona-specific market views used to reduce world_v2 homogenization."""

from __future__ import annotations

from collections import Counter
from typing import Mapping

from .market_diversity_support import (
    coverage_pool,
    crowded_numbers,
    dissent_numbers,
    event_board,
    focus_block,
    performance_board,
    reference_numbers,
    signal_board,
    signal_payloads,
)


MARKET_V2_JUDGE_IDS = ("consensus_judge",)
METAPHYSICS_GROUPS = frozenset({"metaphysics", "hybrid"})


def build_social_prompt_view(
    agent_id: str,
    signal_outputs,
    social_posts,
    performance: Mapping[str, Mapping[str, object]],
    strategy_groups: Mapping[str, str],
) -> dict[str, str]:
    crowded = crowded_numbers(signal_outputs, social_posts, [])
    payloads = signal_payloads(signal_outputs, strategy_groups)
    if agent_id == "social_risk_feed":
        return {
            "signal_board": signal_board(payloads, drop_numbers=set(crowded[:3])),
            "leaderboard": performance_board(performance, strategy_groups),
            "market_focus": focus_block(
                "risk", crowded, dissent_numbers(payloads), coverage_pool(payloads)
            ),
            "instruction": (
                "You are the risk feed. Spotlight crowding, one-track repetition, "
                "and fragile numbers with narrow support instead of echoing the core consensus."
            ),
        }
    return {
        "signal_board": signal_board(payloads),
        "leaderboard": performance_board(performance, strategy_groups),
        "market_focus": focus_block("consensus", crowded, dissent_numbers(payloads), []),
        "instruction": (
            "You are the consensus feed. Amplify the clearest cross-group agreements, "
            "but only when they are supported by more than one signal path."
        ),
    }


def build_bettor_prompt_view(
    agent_id: str,
    signal_outputs,
    social_posts,
    market_ranks,
    strategy_groups: Mapping[str, str],
) -> dict[str, str]:
    payloads = signal_payloads(signal_outputs, strategy_groups)
    crowded = crowded_numbers(signal_outputs, social_posts, market_ranks)
    dissent = dissent_numbers(payloads)
    coverage = coverage_pool(payloads)
    profile = _bettor_profile(agent_id, crowded, dissent, coverage)
    return {
        "signal_board": signal_board(
            payloads,
            allowed_groups=profile["groups"],
            drop_numbers=profile["drop_numbers"],
        ),
        "social_feed": event_board(
            social_posts,
            keep_actor_ids=profile["social_ids"],
        ),
        "judge_boards": event_board(
            market_ranks,
            keep_actor_ids=profile["judge_ids"],
        ),
        "market_focus": focus_block(profile["focus"], crowded, dissent, coverage),
        "instruction": profile["instruction"],
    }


def build_bettor_diversity_summary(bet_plans: Mapping[str, Mapping[str, object]]) -> list[str]:
    tickets = [reference_numbers(plan) for plan in bet_plans.values()]
    unique = {tuple(numbers) for numbers in tickets if numbers}
    counter = Counter(number for numbers in tickets for number in numbers)
    crowded = [f"{number}x{count}" for number, count in counter.most_common(6)]
    return [
        f"bettor_plan_count={len(bet_plans)}",
        f"unique_reference_tickets={len(unique)}",
        f"top_bet_numbers={', '.join(crowded) or '-'}",
    ]


def _bettor_profile(agent_id: str, crowded: list[int], dissent: list[int], coverage: list[int]) -> dict[str, object]:
    profiles = {
        "bettor_conservative": {
            "focus": "stable",
            "groups": None,
            "drop_numbers": (),
            "social_ids": ("social_consensus_feed",),
            "judge_ids": MARKET_V2_JUDGE_IDS,
            "instruction": (
                f"Prefer the stable core {crowded[:4]} and keep expansion tight. "
                "Only add protection if it directly defends the main leg."
            ),
        },
        "bettor_coverage": {
            "focus": "coverage",
            "groups": None,
            "drop_numbers": (),
            "social_ids": ("social_consensus_feed", "social_risk_feed"),
            "judge_ids": (),
            "instruction": (
                f"Use the coverage pool {coverage[:6]} to spread across legs. "
                "Do not collapse everything into one repeated five-number core."
            ),
        },
        "bettor_upside": {
            "focus": "upside",
            "groups": None,
            "drop_numbers": tuple(crowded[:3]),
            "social_ids": ("social_risk_feed",),
            "judge_ids": (),
            "instruction": (
                f"Hunt under-owned upside from {dissent[:6] or coverage[:6]}. "
                "The crowded core is secondary unless you can justify explosive payoff."
            ),
        },
        "bettor_contrarian": {
            "focus": "contrarian",
            "groups": None,
            "drop_numbers": tuple(crowded[:4]),
            "social_ids": ("social_risk_feed",),
            "judge_ids": (),
            "instruction": (
                f"Avoid the crowded core {crowded[:4]}. Build around dissenting numbers "
                f"{dissent[:6] or coverage[:6]} and justify why the market is over-owned."
            ),
        },
        "bettor_follower": {
            "focus": "follower",
            "groups": None,
            "drop_numbers": (),
            "social_ids": ("social_consensus_feed",),
            "judge_ids": MARKET_V2_JUDGE_IDS,
            "instruction": (
                f"Track the crowd leaders {crowded[:5]}. Reusing the dominant core is acceptable "
                "when the market looks coherent."
            ),
        },
        "bettor_ziwei_believer": {
            "focus": "ziwei",
            "groups": METAPHYSICS_GROUPS,
            "drop_numbers": (),
            "social_ids": (),
            "judge_ids": (),
            "instruction": (
                "Treat metaphysics and hybrid signals as primary evidence. "
                "Ignore purely data-driven hot takes when they conflict with chart narratives."
            ),
        },
        "bettor_syndicate": {
            "focus": "syndicate",
            "groups": None,
            "drop_numbers": (),
            "social_ids": ("social_consensus_feed", "social_risk_feed"),
            "judge_ids": MARKET_V2_JUDGE_IDS,
            "instruction": (
                f"Split the bankroll between a market core {crowded[:4]} and a hedge pool "
                f"{coverage[:6] or dissent[:6]}. Show why the structure diversifies exposure."
            ),
        },
        "bettor_handbook_advisor": {
            "focus": "contrarian",
            "groups": None,
            "drop_numbers": tuple(crowded[:3]),
            "social_ids": ("social_risk_feed",),
            "judge_ids": (),
            "instruction": (
                "Follow the handbook doctrine first: avoid public-looking number shapes, "
                "avoid crowding, and prefer plans that reduce prize splitting exposure."
            ),
        },
    }
    return profiles.get(agent_id, profiles["bettor_conservative"])
