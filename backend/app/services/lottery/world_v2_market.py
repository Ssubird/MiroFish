"""Typed helpers for the World V2 market runtime."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from .happy8_rules import TICKET_COST_YUAN
from .models import BetLeg, BetPlan, SignalOutput, StrategyPrediction
from .purchase_structures import PLAN_TYPE_PORTFOLIO, TicketStructure


SOCIAL_POST_WEIGHT = 1.6
JUDGE_BOARD_WEIGHT = 2.4
BET_NUMBER_WEIGHT = 1.2
HEDGE_POOL_SIZE = 8


def signal_output_from_prediction(
    prediction: StrategyPrediction,
    performance_row: Mapping[str, object] | None = None,
) -> SignalOutput:
    scores = _signal_number_scores(prediction, performance_row or {})
    metadata = dict(prediction.metadata or {})
    play_size_bias = _int_or_none(metadata.get("play_size_bias"))
    evidence_refs = tuple(_string_list(metadata.get("sources"))[:4])
    structure_bias = str(metadata.get("structure_bias", "tickets")).strip() or "tickets"
    regime_label = str(metadata.get("regime_label", prediction.group)).strip() or prediction.group
    public_post = str(metadata.get("post", prediction.rationale)).strip() or prediction.rationale
    return SignalOutput(
        strategy_id=prediction.strategy_id,
        number_scores=scores,
        play_size_bias=play_size_bias,
        structure_bias=structure_bias,
        regime_label=regime_label,
        evidence_refs=evidence_refs,
        public_post=public_post,
    )


def serialize_signal_output(output: SignalOutput) -> dict[str, object]:
    payload = asdict(output)
    payload["number_scores"] = {str(key): float(value) for key, value in output.number_scores.items()}
    payload["evidence_refs"] = list(output.evidence_refs)
    return payload


def deserialize_signal_output(payload: Mapping[str, object]) -> SignalOutput:
    raw_scores = payload.get("number_scores") or {}
    if not isinstance(raw_scores, Mapping):
        raise ValueError(f"signal_output.number_scores must be a mapping: {payload}")
    scores = {int(key): float(value) for key, value in raw_scores.items()}
    return SignalOutput(
        strategy_id=str(payload.get("strategy_id", "")).strip(),
        number_scores=scores,
        play_size_bias=_int_or_none(payload.get("play_size_bias")),
        structure_bias=str(payload.get("structure_bias", "tickets")).strip() or "tickets",
        regime_label=str(payload.get("regime_label", "")).strip(),
        evidence_refs=tuple(_string_list(payload.get("evidence_refs"))),
        public_post=str(payload.get("public_post", "")).strip(),
    )


def bet_plan_from_payload(
    persona_id: str,
    payload: Mapping[str, object],
    structure: TicketStructure,
) -> BetPlan:
    return BetPlan(
        persona_id=persona_id,
        legs=tuple(_plan_legs(payload, structure)),
        total_cost_yuan=len(structure.tickets) * TICKET_COST_YUAN,
        play_size_review=_string_map(payload.get("play_size_review")),
        risk_exposure=_risk_label(payload, structure),
        rationale=str(payload.get("rationale", "")).strip() or str(payload.get("comment", "")).strip(),
    )


def serialize_bet_plan(
    plan: BetPlan,
    payload: Mapping[str, object],
    structure: TicketStructure,
    display_name: str,
) -> dict[str, object]:
    data = dict(payload)
    data.update(
        {
            "role_id": plan.persona_id,
            "display_name": display_name,
            "ticket_count": len(structure.tickets),
            "total_cost_yuan": plan.total_cost_yuan,
            "plan_type": structure.plan_type,
            "play_size": structure.play_size,
            "plan_structure": dict(structure.summary),
            "expanded_tickets": [list(ticket) for ticket in structure.tickets],
            "legs": [asdict(item) for item in plan.legs],
            "play_size_review": dict(plan.play_size_review),
            "risk_exposure": plan.risk_exposure,
            "rationale": plan.rationale,
        }
    )
    return data


def market_synthesis_payload(
    signal_outputs: list[dict[str, object]],
    social_posts: list[dict[str, object]],
    judge_boards: list[dict[str, object]],
    bet_plans: dict[str, dict[str, object]],
    reference_plan_id: str,
    reference_plan: Mapping[str, object],
    rationale: str,
) -> dict[str, object]:
    number_scores = aggregate_number_scores(signal_outputs, social_posts, judge_boards, bet_plans)
    reference_leg = reference_leg_payload(reference_plan)
    hedge_pool = [
        number
        for number, _ in sorted(number_scores.items(), key=lambda item: (-item[1], item[0]))
        if number not in reference_leg["numbers"]
    ][:HEDGE_POOL_SIZE]
    total_volume = sum(int(plan.get("total_cost_yuan", 0) or 0) for plan in bet_plans.values())
    return {
        "reference_plan_id": reference_plan_id,
        "reference_plan": dict(reference_plan),
        "reference_leg": reference_leg,
        "hedge_pool": hedge_pool,
        "consensus_number_scores": [
            {"number": number, "score": round(score, 4)}
            for number, score in sorted(number_scores.items(), key=lambda item: (-item[1], item[0]))
        ],
        "total_market_volume_yuan": total_volume,
        "active_bettor_count": len(bet_plans),
        "trusted_strategy_ids": list(reference_plan.get("trusted_strategy_ids", [])),
        "rationale": rationale.strip(),
    }


def compatibility_projection(
    market_synthesis: Mapping[str, object],
    compatibility_plan: Mapping[str, object],
) -> dict[str, object]:
    reference_leg = dict(market_synthesis.get("reference_leg", {}))
    hedge_pool = [int(value) for value in market_synthesis.get("hedge_pool", [])]
    ensemble_numbers = [int(value) for value in reference_leg.get("numbers", [])]
    judge_decision = {
        "primary_numbers": ensemble_numbers,
        "alternate_numbers": hedge_pool,
        "trusted_strategy_ids": list(market_synthesis.get("trusted_strategy_ids", [])),
        "rationale": str(market_synthesis.get("rationale", "")).strip(),
        "reference_plan_id": market_synthesis.get("reference_plan_id"),
    }
    return {
        "ensemble_numbers": ensemble_numbers,
        "alternate_numbers": hedge_pool,
        "judge_decision": judge_decision,
        "purchase_plan": dict(compatibility_plan),
    }


def aggregate_number_scores(
    signal_outputs: list[dict[str, object]],
    social_posts: list[dict[str, object]],
    judge_boards: list[dict[str, object]],
    bet_plans: Mapping[str, Mapping[str, object]],
) -> dict[int, float]:
    scores = {number: 0.0 for number in range(1, 81)}
    for item in signal_outputs:
        raw_scores = item.get("number_scores") or {}
        if isinstance(raw_scores, Mapping):
            for key, value in raw_scores.items():
                scores[int(key)] += float(value)
    for post in social_posts:
        for number in _event_numbers(post, "highlighted_numbers"):
            scores[number] += SOCIAL_POST_WEIGHT
    for board in judge_boards:
        for index, number in enumerate(_event_numbers(board)):
            scores[number] += max(JUDGE_BOARD_WEIGHT - index * 0.2, 0.4)
    for plan in bet_plans.values():
        ticket_weight = _bet_ticket_weight(plan)
        for ticket in _unique_plan_tickets(plan):
            for index, number in enumerate(ticket):
                scores[number] += max(BET_NUMBER_WEIGHT - index * 0.1, 0.3) * ticket_weight
    return {number: score for number, score in scores.items() if score > 0}


def reference_leg_payload(plan: Mapping[str, object]) -> dict[str, object]:
    legs = plan.get("legs") or []
    if isinstance(legs, list) and legs:
        first = legs[0]
        if isinstance(first, Mapping):
            return {
                "plan_type": str(first.get("plan_type", plan.get("plan_type", ""))).strip(),
                "play_size": int(first.get("play_size", plan.get("play_size", 0) or 0)),
                "numbers": [int(value) for value in first.get("numbers", [])],
                "banker_numbers": [int(value) for value in first.get("banker_numbers") or []],
                "drag_numbers": [int(value) for value in first.get("drag_numbers") or []],
            }
    numbers = _reference_numbers(plan)
    return {
        "plan_type": str(plan.get("plan_type", "")).strip(),
        "play_size": int(plan.get("play_size", len(numbers)) or len(numbers)),
        "numbers": numbers,
        "banker_numbers": [int(value) for value in plan.get("banker_numbers") or []],
        "drag_numbers": [int(value) for value in plan.get("drag_numbers") or []],
    }


def _signal_number_scores(
    prediction: StrategyPrediction,
    performance_row: Mapping[str, object],
) -> dict[int, float]:
    rank_bonus = 1.0 / max(int(performance_row.get("rank", 1) or 1), 1)
    if prediction.ranked_scores:
        return {
            int(number): float(score) + rank_bonus
            for number, score in prediction.ranked_scores
        }
    base = len(prediction.numbers)
    return {
        int(number): float(base - index) + rank_bonus
        for index, number in enumerate(prediction.numbers)
    }


def _plan_legs(payload: Mapping[str, object], structure: TicketStructure) -> list[BetLeg]:
    if structure.plan_type == PLAN_TYPE_PORTFOLIO:
        return _portfolio_legs(payload)
    return [_single_leg(payload, structure.play_size, structure.plan_type)]


def _portfolio_legs(payload: Mapping[str, object]) -> list[BetLeg]:
    raw_legs = payload.get("portfolio_legs") or []
    if not isinstance(raw_legs, list):
        return []
    legs = []
    for item in raw_legs:
        if not isinstance(item, Mapping):
            continue
        legs.append(
            BetLeg(
                play_size=int(item.get("play_size", 0) or 0),
                plan_type=str(item.get("plan_type", "")).strip(),
                numbers=tuple(_reference_numbers(item)),
                banker_numbers=tuple(int(value) for value in item.get("banker_numbers") or []) or None,
                drag_numbers=tuple(int(value) for value in item.get("drag_numbers") or []) or None,
                multiple=1,
                rationale=str(item.get("rationale", "")).strip() or str(item.get("comment", "")).strip(),
            )
        )
    return legs


def _single_leg(payload: Mapping[str, object], play_size: int, plan_type: str) -> BetLeg:
    return BetLeg(
        play_size=play_size,
        plan_type=plan_type,
        numbers=tuple(_reference_numbers(payload)),
        banker_numbers=tuple(int(value) for value in payload.get("banker_numbers") or []) or None,
        drag_numbers=tuple(int(value) for value in payload.get("drag_numbers") or []) or None,
        multiple=1,
        rationale=str(payload.get("rationale", "")).strip() or str(payload.get("comment", "")).strip(),
    )


def _reference_numbers(payload: Mapping[str, object]) -> list[int]:
    for key in ("primary_ticket", "wheel_numbers", "candidate_numbers"):
        numbers = _int_list(payload.get(key))
        if numbers:
            return numbers
    numbers = _int_list(payload.get("banker_numbers"))
    for value in _int_list(payload.get("drag_numbers")):
        if value not in numbers:
            numbers.append(value)
    return numbers


def _event_numbers(payload: Mapping[str, object], key: str = "numbers") -> list[int]:
    if isinstance(payload, Mapping):
        metadata = payload.get("metadata") or {}
        if isinstance(metadata, Mapping) and key != "numbers":
            return _int_list(metadata.get(key))
        return _int_list(payload.get(key))
    metadata = getattr(payload, "metadata", {}) or {}
    if isinstance(metadata, Mapping) and key != "numbers":
        return _int_list(metadata.get(key))
    return _int_list(getattr(payload, key, None))


def _risk_label(payload: Mapping[str, object], structure: TicketStructure) -> str:
    explicit = str(payload.get("risk_exposure", "")).strip()
    if explicit:
        return explicit
    if structure.plan_type == "portfolio":
        return "balanced"
    if structure.plan_type == "wheel":
        return "broad"
    if structure.plan_type == "dan_tuo":
        return "aggressive"
    return "focused"


def _bet_ticket_weight(plan: Mapping[str, object]) -> float:
    unique_tickets = _unique_plan_tickets(plan)
    if not unique_tickets:
        return 1.0
    diversity_bonus = 1.0 + min(len(unique_tickets) - 1, 4) * 0.15
    return diversity_bonus / len(unique_tickets)


def _unique_plan_tickets(plan: Mapping[str, object]) -> list[tuple[int, ...]]:
    expanded = plan.get("expanded_tickets")
    if isinstance(expanded, list):
        seen = []
        for ticket in expanded:
            if not isinstance(ticket, list):
                continue
            normalized = tuple(int(value) for value in ticket)
            if normalized not in seen:
                seen.append(normalized)
        return seen
    reference = tuple(reference_leg_payload(plan).get("numbers", []))
    return [reference] if reference else []


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows = []
    for value in raw:
        item = str(value).strip()
        if item and item not in rows:
            rows.append(item)
    return rows


def _string_map(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _int_list(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    values = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value not in values:
            values.append(value)
    return values


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
