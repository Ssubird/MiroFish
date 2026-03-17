"""Canonical purchase structures for Happy 8 plans."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb

from .happy8_rules import play_rule


PLAN_TYPE_TICKETS = "tickets"
PLAN_TYPE_WHEEL = "wheel"
PLAN_TYPE_DAN_TUO = "dan_tuo"
PLAN_TYPE_PORTFOLIO = "portfolio"
PORTFOLIO_LEG_LIMIT = 6


@dataclass(frozen=True)
class TicketStructure:
    plan_type: str
    play_size: int
    tickets: tuple[tuple[int, ...], ...]
    summary: dict[str, object]


def deterministic_tickets(
    scores: dict[int, float],
    preferred: list[int],
    pick_size: int,
    pool_size: int,
    max_tickets: int,
) -> TicketStructure:
    pool = _ticket_pool(scores, preferred, pool_size)
    ranked = sorted(combinations(pool, pick_size), key=lambda item: _combo_key(item, scores), reverse=True)
    tickets = tuple(tuple(sorted(ticket)) for ticket in ranked[:max_tickets])
    return TicketStructure(
        plan_type=PLAN_TYPE_TICKETS,
        play_size=pick_size,
        tickets=tickets,
        summary={
            "play_size": pick_size,
            "play_label": play_rule(pick_size).label,
            "tickets": [list(ticket) for ticket in tickets],
            "pool_numbers": pool,
            "combination_count": len(tickets),
            "ticket_count": len(tickets),
        },
    )


def planner_structure(
    planner: dict[str, object],
    default_pick_size: int,
    max_tickets: int,
) -> TicketStructure:
    plan_type = _plan_type(planner)
    if plan_type == PLAN_TYPE_PORTFOLIO:
        return _portfolio_plan(planner, default_pick_size, max_tickets)
    return _single_structure(planner, default_pick_size, max_tickets, plan_type)


def _single_structure(
    planner: dict[str, object],
    default_pick_size: int,
    max_tickets: int,
    plan_type: str | None = None,
) -> TicketStructure:
    active_type = plan_type or _plan_type(planner)
    play_size = _play_size(planner, default_pick_size)
    if active_type == PLAN_TYPE_TICKETS:
        return _ticket_plan(planner, play_size, max_tickets)
    if active_type == PLAN_TYPE_WHEEL:
        return _wheel_plan(planner, play_size, max_tickets)
    return _dan_tuo_plan(planner, play_size, max_tickets)


def _portfolio_plan(
    planner: dict[str, object],
    default_pick_size: int,
    max_tickets: int,
) -> TicketStructure:
    raw_legs = planner.get("portfolio_legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("plan_type=portfolio requires portfolio_legs")
    legs = []
    tickets: list[tuple[int, ...]] = []
    for index, raw_leg in enumerate(raw_legs[:PORTFOLIO_LEG_LIMIT], start=1):
        if not isinstance(raw_leg, dict):
            raise ValueError(f"portfolio leg must be an object: {raw_leg}")
        leg = _single_structure(raw_leg, default_pick_size, max_tickets)
        tickets.extend(leg.tickets)
        _validate_ticket_count(len(tickets), max_tickets, "portfolio")
        legs.append(_leg_summary(index, leg))
    if not legs:
        raise ValueError("portfolio_legs did not produce any valid ticket")
    return TicketStructure(
        plan_type=PLAN_TYPE_PORTFOLIO,
        play_size=0,
        tickets=tuple(tickets),
        summary={
            "portfolio_legs": legs,
            "ticket_count": len(tickets),
            "combination_count": len(tickets),
            "play_sizes": sorted({int(item["play_size"]) for item in legs}),
        },
    )


def _leg_summary(index: int, leg: TicketStructure) -> dict[str, object]:
    return {
        "index": index,
        "plan_type": leg.plan_type,
        **dict(leg.summary),
    }


def _plan_type(planner: dict[str, object]) -> str:
    value = str(planner.get("plan_type", "")).strip().lower()
    if value not in {PLAN_TYPE_TICKETS, PLAN_TYPE_WHEEL, PLAN_TYPE_DAN_TUO, PLAN_TYPE_PORTFOLIO}:
        raise ValueError("purchase planner must return plan_type=tickets|wheel|dan_tuo|portfolio")
    return value


def _play_size(planner: dict[str, object], default_pick_size: int) -> int:
    raw = planner.get("play_size", default_pick_size)
    try:
        play_size = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid purchase play_size: {raw}") from exc
    play_rule(play_size)  # validates range 1-10
    return play_size


def _ticket_plan(planner: dict[str, object], play_size: int, max_tickets: int) -> TicketStructure:
    tickets = _ticket_list(planner.get("tickets"), play_size)
    if not tickets:
        primary = _flat_numbers(planner.get("primary_ticket"), play_size)
        if len(primary) != play_size:
            raise ValueError("plan_type=tickets requires tickets or a primary_ticket matching play_size")
        tickets = (tuple(primary),)
    _validate_ticket_count(len(tickets), max_tickets, "tickets")
    return TicketStructure(
        plan_type=PLAN_TYPE_TICKETS,
        play_size=play_size,
        tickets=tickets,
        summary=_base_summary(play_size) | {
            "tickets": [list(ticket) for ticket in tickets],
            "combination_count": len(tickets),
            "ticket_count": len(tickets),
        },
    )


def _wheel_plan(planner: dict[str, object], play_size: int, max_tickets: int) -> TicketStructure:
    wheel_numbers = _flat_numbers(planner.get("wheel_numbers"), _max_pool_size(max_tickets, play_size))
    if len(wheel_numbers) < play_size:
        raise ValueError("plan_type=wheel requires wheel_numbers to cover the selected play_size")
    combination_count = comb(len(wheel_numbers), play_size)
    _validate_ticket_count(combination_count, max_tickets, "wheel")
    tickets = tuple(tuple(sorted(ticket)) for ticket in combinations(wheel_numbers, play_size))
    return TicketStructure(
        plan_type=PLAN_TYPE_WHEEL,
        play_size=play_size,
        tickets=tickets,
        summary=_base_summary(play_size) | {
            "wheel_numbers": wheel_numbers,
            "combination_count": combination_count,
            "ticket_count": combination_count,
        },
    )


def _dan_tuo_plan(planner: dict[str, object], play_size: int, max_tickets: int) -> TicketStructure:
    banker_numbers = _flat_numbers(planner.get("banker_numbers"), play_size - 1)
    drag_numbers = [number for number in _flat_numbers(planner.get("drag_numbers"), _max_pool_size(max_tickets, play_size)) if number not in banker_numbers]
    if not banker_numbers:
        raise ValueError("plan_type=dan_tuo requires banker_numbers")
    if len(banker_numbers) >= play_size:
        raise ValueError("banker_numbers must be smaller than play_size")
    remaining = play_size - len(banker_numbers)
    if len(drag_numbers) < remaining:
        raise ValueError("drag_numbers are insufficient for the selected play_size")
    combination_count = comb(len(drag_numbers), remaining)
    _validate_ticket_count(combination_count, max_tickets, "dan_tuo")
    tickets = tuple(tuple(sorted([*banker_numbers, *combo])) for combo in combinations(drag_numbers, remaining))
    return TicketStructure(
        plan_type=PLAN_TYPE_DAN_TUO,
        play_size=play_size,
        tickets=tickets,
        summary=_base_summary(play_size) | {
            "banker_numbers": banker_numbers,
            "drag_numbers": drag_numbers,
            "combination_count": combination_count,
            "ticket_count": combination_count,
        },
    )


def _base_summary(play_size: int) -> dict[str, object]:
    rule = play_rule(play_size)
    return {"play_size": play_size, "play_label": rule.label}


def _validate_ticket_count(ticket_count: int, max_tickets: int, label: str) -> None:
    if ticket_count <= 0:
        raise ValueError(f"{label} expansion did not produce any valid ticket")
    if ticket_count > max_tickets:
        raise ValueError(f"{label} expands to {ticket_count} tickets, exceeding budget limit {max_tickets}")


def _ticket_list(raw: object, play_size: int) -> tuple[tuple[int, ...], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tickets must be a two-dimensional array")
    tickets = []
    for item in raw:
        numbers = _flat_numbers(item, play_size)
        if len(numbers) != play_size:
            raise ValueError(f"ticket length must equal play_size={play_size}: {item}")
        tickets.append(tuple(numbers))
    return tuple(tickets)


def _flat_numbers(raw: object, limit: int) -> list[int]:
    if not isinstance(raw, list):
        return []
    numbers = []
    for value in raw:
        if isinstance(value, list):
            raise ValueError(f"number payload must be one-dimensional: {raw}")
        number = int(value)
        if 1 <= number <= 80 and number not in numbers:
            numbers.append(number)
        if len(numbers) >= limit:
            break
    return numbers


def _ticket_pool(scores: dict[int, float], preferred: list[int], pool_size: int) -> list[int]:
    ordered = [number for number, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:pool_size]]
    return sorted(list(dict.fromkeys(preferred + ordered))[: max(pool_size, len(preferred))])


def _combo_key(ticket: tuple[int, ...], scores: dict[int, float]) -> tuple[float, int]:
    return (sum(scores[number] for number in ticket), -sum(ticket))


def _max_pool_size(max_tickets: int, play_size: int) -> int:
    """Compute the largest pool size whose C(n, play_size) <= max_tickets."""
    MAX_POOL_CEILING = 80
    for n in range(play_size, MAX_POOL_CEILING + 1):
        if comb(n, play_size) > max_tickets:
            return n - 1
    return MAX_POOL_CEILING
