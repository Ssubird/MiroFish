"""Game-kernel interfaces for lottery worlds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpandedPlan:
    game_id: str
    plan_type: str
    play_size: int
    tickets: tuple[tuple[int, ...], ...]
    summary: Mapping[str, Any]
    cost_yuan: int


@dataclass(frozen=True)
class SettlementResult:
    game_id: str
    payout_yuan: float
    profit_yuan: float
    roi: float
    ticket_hits: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketFeatureProfile:
    game_id: str
    play_mode: str
    feature_extractors: tuple[str, ...]
    crowding_rules: tuple[str, ...]
    payout_surrogate_weights: Mapping[str, float]


class GameDefinition(Protocol):
    game_id: str
    name: str
    number_domain: tuple[int, ...]

    def validate_selection(self, play_mode: str, numbers: list[int]) -> ValidationResult: ...

    def expand_plan(self, plan: Mapping[str, Any], pick_size: int, max_tickets: int) -> ExpandedPlan: ...

    def price_plan(self, plan: ExpandedPlan) -> int: ...

    def settle_plan(self, draw_numbers: tuple[int, ...], plan: ExpandedPlan) -> SettlementResult: ...

    def extract_features(self, selection: list[int], play_mode: str) -> Mapping[str, float]: ...
