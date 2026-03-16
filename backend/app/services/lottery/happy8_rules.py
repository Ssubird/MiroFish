"""Happy 8 purchase rules shared by planning and settlement."""

from __future__ import annotations

from dataclasses import dataclass


TICKET_COST_YUAN = 2
DEFAULT_BUDGET_YUAN = 50
MIN_BUDGET_YUAN = TICKET_COST_YUAN
MAX_BUDGET_YUAN = 500
ALLOWED_PLAY_SIZES = (3, 4, 5, 6)
PAYOUT_BY_PLAY_SIZE = {
    3: {2: 3, 3: 53},
    4: {2: 3, 3: 5, 4: 100},
    5: {3: 3, 4: 21, 5: 1000},
    6: {3: 3, 4: 10, 5: 30, 6: 3000},
}


@dataclass(frozen=True)
class Happy8PlayRule:
    play_size: int
    payouts: dict[int, int]

    @property
    def label(self) -> str:
        return f"选{self.play_size}"


def play_rule(play_size: int) -> Happy8PlayRule:
    normalized = int(play_size)
    if normalized not in ALLOWED_PLAY_SIZES:
        raise ValueError(f"Happy 8 purchase play_size must be one of {ALLOWED_PLAY_SIZES}")
    return Happy8PlayRule(normalized, dict(PAYOUT_BY_PLAY_SIZE[normalized]))


def ticket_payout(play_size: int, hits: int) -> int:
    return int(PAYOUT_BY_PLAY_SIZE.get(int(play_size), {}).get(int(hits), 0))


def play_rule_lines() -> tuple[str, ...]:
    rows = []
    for play_size in ALLOWED_PLAY_SIZES:
        payouts = ", ".join(
            f"中{hits}={amount}元"
            for hits, amount in sorted(PAYOUT_BY_PLAY_SIZE[play_size].items())
        )
        rows.append(f"- 选{play_size}: {payouts}")
    return tuple(rows)
