"""Recent draw statistics for the lottery world UI."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from .models import DrawRecord


RECENT_DRAW_WINDOW = 50
RECENT_PERIOD_LIMIT = 8
RECENT_MENTION_LIMIT = 4


def build_recent_draw_stats(
    completed_draws: Iterable[DrawRecord],
    timeline_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    draws = list(completed_draws)[-RECENT_DRAW_WINDOW:]
    counts = Counter()
    periods = defaultdict(list)
    for draw in draws:
        for number in draw.numbers:
            counts[int(number)] += 1
            periods[int(number)].append(draw.period)
    mentions = _number_mentions(timeline_rows)
    rows = [_number_row(number, draws, counts, periods, mentions) for number in range(1, 81)]
    ranked = sorted(rows, key=lambda item: (-item["count"], item["number"]))
    return {
        "window_size": len(draws),
        "from_period": draws[0].period if draws else None,
        "to_period": draws[-1].period if draws else None,
        "hot_numbers": [item["number"] for item in ranked[:10]],
        "cold_numbers": [item["number"] for item in sorted(rows, key=lambda item: (item["count"], item["number"]))[:10]],
        "numbers": rows,
    }


def _number_row(
    number: int,
    draws: list[DrawRecord],
    counts: Counter,
    periods: dict[int, list[str]],
    mentions: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    period_rows = list(periods[number])[-RECENT_PERIOD_LIMIT:]
    mention = mentions.get(number, {})
    return {
        "number": number,
        "count": int(counts[number]),
        "periods": period_rows,
        "last_seen_period": period_rows[-1] if period_rows else None,
        "mentioned_by": mention.get("actors", []),
        "mention_count": int(mention.get("count", 0)),
        "active": bool(draws and number in draws[-1].numbers),
    }


def _number_mentions(timeline_rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    counts = Counter()
    actors = defaultdict(Counter)
    for row in timeline_rows:
        actor_id = str(row.get("actor_id", "")).strip()
        for value in row.get("numbers", []) or []:
            number = int(value)
            counts[number] += 1
            if actor_id:
                actors[number][actor_id] += 1
    return {
        number: {
            "count": count,
            "actors": [item for item, _ in actors[number].most_common(RECENT_MENTION_LIMIT)],
        }
        for number, count in counts.items()
    }

