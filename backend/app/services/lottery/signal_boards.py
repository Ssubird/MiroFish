"""Canonical signal-board compatibility layer for world_v2 market."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .models import StrategyPrediction


@dataclass(frozen=True)
class SignalBoard:
    """Canonical signal object consumed by the market stages."""

    strategy_id: str
    issue_id: str
    game_id: str
    board_type: str
    number_scores: Mapping[int, float]
    structure_scores: Mapping[str, float]
    play_size_scores: Mapping[str, float]
    crowding_penalties: Mapping[str, float]
    payout_surrogates: Mapping[str, float]
    exclusions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    rationale: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["number_scores"] = {str(key): float(value) for key, value in self.number_scores.items()}
        payload["structure_scores"] = {str(key): float(value) for key, value in self.structure_scores.items()}
        payload["play_size_scores"] = {str(key): float(value) for key, value in self.play_size_scores.items()}
        payload["crowding_penalties"] = {str(key): float(value) for key, value in self.crowding_penalties.items()}
        payload["payout_surrogates"] = {str(key): float(value) for key, value in self.payout_surrogates.items()}
        payload["exclusions"] = list(self.exclusions)
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["metadata"] = dict(self.metadata)
        return payload


def signal_board_from_prediction(
    prediction: StrategyPrediction,
    *,
    issue_id: str,
    game_id: str,
    number_scores: Mapping[int, float],
    structure_scores: Mapping[str, float],
    play_size_scores: Mapping[str, float],
    crowding_penalties: Mapping[str, float],
    payout_surrogates: Mapping[str, float],
    exclusions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    confidence: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
) -> SignalBoard:
    return SignalBoard(
        strategy_id=prediction.strategy_id,
        issue_id=issue_id,
        game_id=game_id,
        board_type=prediction.group,
        number_scores=dict(number_scores),
        structure_scores=dict(structure_scores),
        play_size_scores=dict(play_size_scores),
        crowding_penalties=dict(crowding_penalties),
        payout_surrogates=dict(payout_surrogates),
        exclusions=tuple(exclusions or ()),
        evidence_refs=tuple(evidence_refs or ()),
        confidence=round(float(confidence), 4),
        rationale=str(prediction.rationale).strip(),
        metadata={"display_name": prediction.display_name, "kind": prediction.kind, **dict(metadata or {})},
    )


def serialize_signal_boards(boards: list[SignalBoard]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in boards]


def top_numbers(board: Mapping[str, Any], limit: int = 8) -> list[int]:
    scores = board.get("number_scores") or {}
    pairs = [(int(key), float(value)) for key, value in scores.items()]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return [number for number, _ in pairs[:limit]]
