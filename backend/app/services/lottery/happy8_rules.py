"""Happy 8 purchase rules shared by planning and settlement.

Data-driven rule table covering all ten play sizes (选1 through 选10).
Official source: https://www.cwl.gov.cn/fcpz/yxjs/kl8/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


TICKET_COST_YUAN = 2
DEFAULT_BUDGET_YUAN = 50
MIN_BUDGET_YUAN = TICKET_COST_YUAN
MAX_BUDGET_YUAN = 500
MAX_MULTIPLE = 15
MIN_PLAY_SIZE = 1
MAX_PLAY_SIZE = 10
ALLOWED_PLAY_SIZES = tuple(range(MIN_PLAY_SIZE, MAX_PLAY_SIZE + 1))

# Payout tables keyed by (play_size -> {hits: payout_yuan}).
# 选5~选10: hitting 0 numbers awards a consolation prize of 2 yuan.
PAYOUT_BY_PLAY_SIZE: Mapping[int, Mapping[int, float]] = {
    1: {1: 4.6},
    2: {2: 19},
    3: {2: 3, 3: 53},
    4: {2: 3, 3: 5, 4: 100},
    5: {0: 2, 3: 3, 4: 21, 5: 1000},
    6: {0: 2, 3: 3, 4: 10, 5: 30, 6: 3000},
    7: {0: 2, 3: 1, 4: 5, 5: 21, 6: 300, 7: 10000},
    8: {0: 2, 4: 2, 5: 10, 6: 88, 7: 800, 8: 50000},
    9: {0: 2, 4: 2, 5: 5, 6: 30, 7: 200, 8: 5000, 9: 500000},
    10: {0: 2, 5: 2, 6: 15, 7: 50, 8: 500, 9: 5000, 10: 5000000},
}


@dataclass(frozen=True)
class Happy8PlayRule:
    play_size: int
    payouts: dict[int, float]

    @property
    def label(self) -> str:
        return f"选{self.play_size}"

    @property
    def max_payout(self) -> float:
        return max(self.payouts.values()) if self.payouts else 0

    @property
    def has_consolation(self) -> bool:
        """Whether hitting zero numbers still pays (选5~选10)."""
        return 0 in self.payouts


def play_rule(play_size: int) -> Happy8PlayRule:
    normalized = int(play_size)
    if normalized not in ALLOWED_PLAY_SIZES:
        raise ValueError(
            f"Happy 8 play_size must be between "
            f"{MIN_PLAY_SIZE} and {MAX_PLAY_SIZE}, got {normalized}"
        )
    return Happy8PlayRule(normalized, dict(PAYOUT_BY_PLAY_SIZE[normalized]))


def ticket_payout(play_size: int, hits: int) -> float:
    return float(
        PAYOUT_BY_PLAY_SIZE.get(int(play_size), {}).get(int(hits), 0)
    )


def play_rule_lines() -> tuple[str, ...]:
    rows = []
    for ps in ALLOWED_PLAY_SIZES:
        payouts = ", ".join(
            f"中{hits}={amount}元"
            for hits, amount in sorted(PAYOUT_BY_PLAY_SIZE[ps].items())
        )
        rows.append(f"- 选{ps}: {payouts}")
    return tuple(rows)
