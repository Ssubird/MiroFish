"""Canonical purchase structures for Happy 8 pick-five plans."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb


PLAN_TYPE_TICKETS = "tickets"
PLAN_TYPE_WHEEL = "wheel"
PLAN_TYPE_DAN_TUO = "dan_tuo"
STRUCTURE_NUMBER_LIMIT = 12


@dataclass(frozen=True)
class TicketStructure:
    plan_type: str
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
        tickets=tickets,
        summary={
            "tickets": [list(ticket) for ticket in tickets],
            "pool_numbers": pool,
            "combination_count": len(tickets),
        },
    )


def planner_structure(
    planner: dict[str, object],
    pick_size: int,
    max_tickets: int,
) -> TicketStructure:
    plan_type = _plan_type(planner)
    if plan_type == PLAN_TYPE_TICKETS:
        return _ticket_plan(planner, pick_size, max_tickets)
    if plan_type == PLAN_TYPE_WHEEL:
        return _wheel_plan(planner, pick_size, max_tickets)
    return _dan_tuo_plan(planner, pick_size, max_tickets)


def _plan_type(planner: dict[str, object]) -> str:
    value = str(planner.get("plan_type", "")).strip().lower()
    if value not in {PLAN_TYPE_TICKETS, PLAN_TYPE_WHEEL, PLAN_TYPE_DAN_TUO}:
        raise ValueError("purchase planner 必须返回 plan_type=tickets|wheel|dan_tuo")
    return value


def _ticket_plan(planner: dict[str, object], pick_size: int, max_tickets: int) -> TicketStructure:
    tickets = _ticket_list(planner.get("tickets"), pick_size)
    if not tickets:
        primary = _flat_numbers(planner.get("primary_ticket"), pick_size)
        if len(primary) != pick_size:
            raise ValueError("plan_type=tickets 时必须提供 tickets 或完整 primary_ticket")
        tickets = (tuple(primary),)
    _validate_ticket_count(len(tickets), max_tickets, "显式多注")
    return TicketStructure(
        plan_type=PLAN_TYPE_TICKETS,
        tickets=tickets,
        summary={"tickets": [list(ticket) for ticket in tickets], "combination_count": len(tickets)},
    )


def _wheel_plan(planner: dict[str, object], pick_size: int, max_tickets: int) -> TicketStructure:
    wheel_numbers = _flat_numbers(planner.get("wheel_numbers"), STRUCTURE_NUMBER_LIMIT)
    if len(wheel_numbers) < pick_size:
        raise ValueError("plan_type=wheel 时 wheel_numbers 至少要覆盖单注长度")
    combination_count = comb(len(wheel_numbers), pick_size)
    _validate_ticket_count(combination_count, max_tickets, "复式")
    tickets = tuple(tuple(sorted(ticket)) for ticket in combinations(wheel_numbers, pick_size))
    return TicketStructure(
        plan_type=PLAN_TYPE_WHEEL,
        tickets=tickets,
        summary={
            "wheel_numbers": wheel_numbers,
            "combination_count": combination_count,
        },
    )


def _dan_tuo_plan(planner: dict[str, object], pick_size: int, max_tickets: int) -> TicketStructure:
    banker_numbers = _flat_numbers(planner.get("banker_numbers"), pick_size - 1)
    drag_numbers = [number for number in _flat_numbers(planner.get("drag_numbers"), STRUCTURE_NUMBER_LIMIT) if number not in banker_numbers]
    if not banker_numbers:
        raise ValueError("plan_type=dan_tuo 时 banker_numbers 不能为空")
    if len(banker_numbers) >= pick_size:
        raise ValueError("胆码数量必须小于单注长度")
    remaining = pick_size - len(banker_numbers)
    if len(drag_numbers) < remaining:
        raise ValueError("拖码数量不足，无法组成完整票面")
    combination_count = comb(len(drag_numbers), remaining)
    _validate_ticket_count(combination_count, max_tickets, "胆拖")
    tickets = tuple(
        tuple(sorted([*banker_numbers, *combo]))
        for combo in combinations(drag_numbers, remaining)
    )
    return TicketStructure(
        plan_type=PLAN_TYPE_DAN_TUO,
        tickets=tickets,
        summary={
            "banker_numbers": banker_numbers,
            "drag_numbers": drag_numbers,
            "combination_count": combination_count,
        },
    )


def _validate_ticket_count(ticket_count: int, max_tickets: int, label: str) -> None:
    if ticket_count <= 0:
        raise ValueError(f"{label} 展开后没有有效票面")
    if ticket_count > max_tickets:
        raise ValueError(f"{label} 展开后 {ticket_count} 注，超过预算上限 {max_tickets} 注")


def _ticket_list(raw: object, pick_size: int) -> tuple[tuple[int, ...], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("tickets 必须是二维数组")
    tickets = []
    for item in raw:
        numbers = _flat_numbers(item, pick_size)
        if len(numbers) != pick_size:
            raise ValueError(f"ticket 长度必须等于 {pick_size}: {item}")
        tickets.append(tuple(numbers))
    return tuple(tickets)


def _flat_numbers(raw: object, limit: int) -> list[int]:
    if not isinstance(raw, list):
        return []
    numbers = []
    for value in raw:
        if isinstance(value, list):
            raise ValueError(f"号码结构必须是一维数组: {raw}")
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
