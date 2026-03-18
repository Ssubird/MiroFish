"""Shared helpers for persona-specific market visibility."""

from __future__ import annotations

from collections import Counter
from typing import Mapping

from .world_v2_market import aggregate_number_scores, serialize_signal_output


VISIBLE_SIGNAL_LIMIT = 6
VISIBLE_NUMBER_LIMIT = 6
VISIBLE_EVENT_LIMIT = 6
CROWDING_LIMIT = 8


def crowded_numbers(signal_outputs, social_posts, market_ranks) -> list[int]:
    scores = aggregate_number_scores(
        [_normalize_signal_output(item) for item in signal_outputs],
        [_event_payload(item) for item in social_posts],
        [_event_payload(item) for item in market_ranks],
        {},
    )
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [number for number, _ in ordered][:CROWDING_LIMIT]


def dissent_numbers(payloads: list[dict[str, object]]) -> list[int]:
    counter = Counter(
        number
        for payload in payloads
        for number, _ in payload["top_numbers"][:4]
    )
    ordered = []
    for payload in payloads:
        for number, _ in payload["top_numbers"]:
            if counter[number] == 1 and number not in ordered:
                ordered.append(number)
    return ordered[:CROWDING_LIMIT]


def coverage_pool(payloads: list[dict[str, object]]) -> list[int]:
    ordered = []
    per_group = Counter()
    for payload in sorted(payloads, key=lambda item: (item["group"], item["strategy_id"])):
        for number, _ in payload["top_numbers"]:
            group = str(payload["group"])
            if number in ordered or per_group[group] >= 2:
                continue
            ordered.append(number)
            per_group[group] += 1
            if len(ordered) >= CROWDING_LIMIT:
                return ordered
    return ordered


def signal_payloads(signal_outputs, strategy_groups: Mapping[str, str]) -> list[dict[str, object]]:
    rows = []
    for item in signal_outputs:
        payload = _normalize_signal_output(item)
        rows.append(
            {
                "strategy_id": str(payload.get("strategy_id", "")).strip(),
                "group": str(strategy_groups.get(str(payload.get("strategy_id", "")), "-")).strip() or "-",
                "structure_bias": str(payload.get("structure_bias", "tickets")).strip() or "tickets",
                "play_size_bias": payload.get("play_size_bias"),
                "top_numbers": _top_numbers(payload.get("number_scores") or {}),
            }
        )
    return rows


def signal_board(
    payloads: list[dict[str, object]],
    *,
    allowed_groups: frozenset[str] | None = None,
    drop_numbers: set[int] | tuple[int, ...] = (),
) -> str:
    rows = []
    blocked = set(drop_numbers)
    for payload in payloads[:VISIBLE_SIGNAL_LIMIT]:
        if allowed_groups and payload["group"] not in allowed_groups:
            continue
        numbers = [(number, score) for number, score in payload["top_numbers"] if number not in blocked]
        board = ", ".join(f"{number}:{score:.2f}" for number, score in numbers[:VISIBLE_NUMBER_LIMIT]) or "-"
        rows.append(
            f"- {payload['strategy_id']} [{payload['group']}]: {board}; "
            f"play_bias={payload['play_size_bias']}; structure={payload['structure_bias']}"
        )
    return "\n".join(rows) or "- no visible signals"


def performance_board(
    performance: Mapping[str, Mapping[str, object]],
    strategy_groups: Mapping[str, str],
) -> str:
    rows = []
    ranked = sorted(performance.items(), key=lambda row: int(row[1].get("rank", 999) or 999))
    for strategy_id, item in ranked[:VISIBLE_SIGNAL_LIMIT]:
        rows.append(
            f"- #{item.get('rank', '-')} {strategy_id} [{strategy_groups.get(strategy_id, '-')}] "
            f"objective={float(item.get('objective_score', 0.0)):.3f} "
            f"roi={float(item.get('strategy_roi', 0.0)):.2f}"
        )
    return "\n".join(rows) or "- no settled performance yet"


def event_board(events, *, keep_actor_ids: tuple[str, ...] | None) -> str:
    if keep_actor_ids is not None and not keep_actor_ids:
        return "- no visible events"
    rows = []
    allow = set(keep_actor_ids or [])
    for item in events[-VISIBLE_EVENT_LIMIT:]:
        payload = _event_payload(item)
        if allow and payload["actor_id"] not in allow:
            continue
        rows.append(
            f"- {payload['display_name']} ({payload['actor_id']}): "
            f"numbers={payload['numbers'] or '-'}; comment={payload['comment'] or '-'}"
        )
    return "\n".join(rows) or "- no visible events"


def focus_block(label: str, crowded: list[int], dissent: list[int], coverage: list[int]) -> str:
    if label == "risk":
        return f"Crowded core: {crowded[:6]}\nDissent pool: {dissent[:6] or '-'}"
    if label == "coverage":
        return f"Coverage pool: {coverage[:8] or '-'}\nCrowded core: {crowded[:4]}"
    if label == "upside":
        return f"Under-owned pool: {dissent[:8] or coverage[:8] or '-'}\nCrowded core: {crowded[:4]}"
    if label == "contrarian":
        return f"Fade core: {crowded[:5]}\nContrarian pool: {dissent[:8] or coverage[:8] or '-'}"
    if label == "follower":
        return f"Crowd leaders: {crowded[:6]}\nDissent pool: {dissent[:4] or '-'}"
    if label == "ziwei":
        return f"Metaphysics-led pool: {coverage[:8] or dissent[:8] or '-'}"
    if label == "syndicate":
        return f"Main core: {crowded[:4]}\nHedge pool: {coverage[:8] or dissent[:8] or '-'}"
    return f"Cross-group core: {crowded[:6]}\nSecondary pool: {coverage[:6] or dissent[:6] or '-'}"


def reference_numbers(plan: Mapping[str, object]) -> list[int]:
    legs = plan.get("legs") or []
    if isinstance(legs, list) and legs:
        first = legs[0]
        if isinstance(first, Mapping):
            return [int(value) for value in first.get("numbers", []) or []]
    return [int(value) for value in plan.get("primary_ticket", []) or []]


def _normalize_signal_output(item) -> dict[str, object]:
    return serialize_signal_output(item) if hasattr(item, "strategy_id") else dict(item)


def _event_payload(item) -> dict[str, object]:
    if isinstance(item, Mapping):
        return {
            "actor_id": str(item.get("actor_id", item.get("strategy_id", ""))).strip(),
            "display_name": str(item.get("actor_display_name", item.get("display_name", ""))).strip(),
            "comment": str(item.get("content", item.get("comment", ""))).strip(),
            "numbers": [int(value) for value in item.get("numbers", []) or []],
        }
    return {
        "actor_id": str(getattr(item, "actor_id", "")).strip(),
        "display_name": str(getattr(item, "actor_display_name", "")).strip(),
        "comment": str(getattr(item, "content", "")).strip(),
        "numbers": [int(value) for value in getattr(item, "numbers", []) or []],
    }


def _top_numbers(raw_scores: Mapping[str | int, object]) -> list[tuple[int, float]]:
    rows = [(int(key), float(value)) for key, value in raw_scores.items()]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows[:VISIBLE_NUMBER_LIMIT + 2]
