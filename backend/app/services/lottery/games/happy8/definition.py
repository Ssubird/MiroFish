"""Happy 8 game-kernel implementation."""

from __future__ import annotations

from typing import Any, Mapping

from ...happy8_rules import ALLOWED_PLAY_SIZES, TICKET_COST_YUAN, play_rule, ticket_payout
from ...purchase_structures import planner_structure
from ..base import ExpandedPlan, SettlementResult, ValidationResult
from .features import extract_happy8_features


class Happy8GameDefinition:
    game_id = "happy8"
    name = "Happy 8"
    number_domain = tuple(range(1, 81))

    def validate_selection(self, play_mode: str, numbers: list[int]) -> ValidationResult:
        del play_mode
        unique = sorted({int(value) for value in numbers})
        if len(unique) != len(numbers):
            return ValidationResult(False, ("selection contains duplicate numbers",))
        if not unique:
            return ValidationResult(False, ("selection is empty",))
        if any(number not in self.number_domain for number in unique):
            return ValidationResult(False, ("selection contains out-of-range numbers",))
        play_size = len(unique)
        if play_size not in ALLOWED_PLAY_SIZES:
            return ValidationResult(False, (f"unsupported play size: {play_size}",))
        return ValidationResult(True)

    def expand_plan(self, plan: Mapping[str, Any], pick_size: int, max_tickets: int) -> ExpandedPlan:
        structure = planner_structure(dict(plan), pick_size, max_tickets)
        return ExpandedPlan(
            game_id=self.game_id,
            plan_type=structure.plan_type,
            play_size=structure.play_size,
            tickets=structure.tickets,
            summary=dict(structure.summary),
            cost_yuan=len(structure.tickets) * TICKET_COST_YUAN,
        )

    def price_plan(self, plan: ExpandedPlan) -> int:
        return int(plan.cost_yuan)

    def settle_plan(self, draw_numbers: tuple[int, ...], plan: ExpandedPlan) -> SettlementResult:
        actual = set(draw_numbers)
        ticket_hits = tuple(len(actual & set(ticket)) for ticket in plan.tickets)
        payout = float(sum(ticket_payout(len(ticket), hits) for ticket, hits in zip(plan.tickets, ticket_hits)))
        profit = payout - plan.cost_yuan
        roi = round(profit / plan.cost_yuan, 4) if plan.cost_yuan else 0.0
        return SettlementResult(
            game_id=self.game_id,
            payout_yuan=payout,
            profit_yuan=profit,
            roi=roi,
            ticket_hits=ticket_hits,
            metadata={"ticket_count": len(plan.tickets)},
        )

    def extract_features(self, selection: list[int], play_mode: str) -> Mapping[str, float]:
        return extract_happy8_features(selection, play_mode)

    def play_label(self, play_size: int) -> str:
        return play_rule(play_size).label
