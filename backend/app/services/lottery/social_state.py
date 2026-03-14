"""Persistent social-state tracking for social lottery agents."""

from __future__ import annotations

from dataclasses import dataclass, replace


POST_HISTORY_LIMIT = 4
REVISION_HISTORY_LIMIT = 6
TRUST_NETWORK_LIMIT = 6
SOCIAL_GROUP = "social"
DEFAULT_PERSONAS = {
    "consensus": "Consensus moderator: absorb stable cross-group evidence before posting.",
    "risk": "Risk reviewer: challenge crowding and correlated hot numbers before posting.",
    "report": "Report observer: bring external prediction notes into the public square.",
    "rules": "Rule analyst: translate non-LLM signals into public arguments.",
}


@dataclass(frozen=True)
class SocialAgentState:
    strategy_id: str
    display_name: str
    social_mode: str
    persona: str
    trust_network: tuple[str, ...] = ()
    post_history: tuple[dict[str, object], ...] = ()
    revision_history: tuple[dict[str, object], ...] = ()


class SocialStateTracker:
    """Track persistent persona, trust links, posts, and revisions across issues."""

    def __init__(self, strategies: dict[str, object], seed: dict[str, dict[str, object]] | None = None):
        self._states = {strategy_id: _initial_state(strategy_id, strategy) for strategy_id, strategy in strategies.items()}
        self._load_seed(seed or {})

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {strategy_id: _serialize_state(state) for strategy_id, state in self._states.items()}

    def record_issue(
        self,
        period: str,
        predictions: dict[str, object],
        trace: list[dict[str, object]],
        actual_numbers: tuple[int, ...] | None = None,
    ) -> None:
        self._record_posts(period, predictions, actual_numbers)
        self._record_revisions(period, trace)

    def _record_posts(
        self,
        period: str,
        predictions: dict[str, object],
        actual_numbers: tuple[int, ...] | None,
    ) -> None:
        actual = set(actual_numbers or ())
        for strategy_id, state in self._states.items():
            prediction = predictions.get(strategy_id)
            if prediction is None:
                continue
            metadata = dict(getattr(prediction, "metadata", {}) or {})
            trust_network = _merge_trust(state.trust_network, metadata.get("trusted_strategy_ids", []))
            post = {
                "period": period,
                "numbers": list(prediction.numbers),
                "rationale": prediction.rationale,
                "post": str(metadata.get("post", "")).strip(),
                "trusted_strategy_ids": list(trust_network),
                "hits": len(actual & set(prediction.numbers)) if actual else None,
                "matched_numbers": sorted(actual & set(prediction.numbers)) if actual else [],
            }
            self._states[strategy_id] = replace(
                state,
                trust_network=trust_network,
                post_history=_append_limited(state.post_history, post, POST_HISTORY_LIMIT),
            )

    def _record_revisions(self, period: str, trace: list[dict[str, object]]) -> None:
        for item in _social_revision_items(trace):
            strategy_id = str(item.get("strategy_id", "")).strip()
            state = self._states.get(strategy_id)
            if state is None:
                continue
            revision = {
                "period": period,
                "round": int(item.get("round", 0) or 0),
                "comment": str(item.get("comment", "")).strip(),
                "numbers_before": list(item.get("numbers_before", [])),
                "numbers_after": list(item.get("numbers_after", [])),
                "peer_strategy_ids": list(item.get("peer_strategy_ids", [])),
            }
            self._states[strategy_id] = replace(
                state,
                revision_history=_append_limited(state.revision_history, revision, REVISION_HISTORY_LIMIT),
            )

    def _load_seed(self, seed: dict[str, dict[str, object]]) -> None:
        for strategy_id, payload in seed.items():
            state = self._states.get(strategy_id)
            if state is None:
                continue
            self._states[strategy_id] = replace(
                state,
                trust_network=_as_tuple(payload.get("trust_network")),
                post_history=_as_history(payload.get("post_history"), POST_HISTORY_LIMIT),
                revision_history=_as_history(payload.get("revision_history"), REVISION_HISTORY_LIMIT),
            )


def _initial_state(strategy_id: str, strategy: object) -> SocialAgentState:
    social_mode = str(getattr(strategy, "social_mode", "discussion")).strip() or "discussion"
    persona = DEFAULT_PERSONAS.get(social_mode, "Social analyst: discuss picks with persistent memory.")
    return SocialAgentState(
        strategy_id=strategy_id,
        display_name=str(getattr(strategy, "display_name", strategy_id)),
        social_mode=social_mode,
        persona=persona,
    )


def _serialize_state(state: SocialAgentState) -> dict[str, object]:
    return {
        "strategy_id": state.strategy_id,
        "display_name": state.display_name,
        "social_mode": state.social_mode,
        "persona": state.persona,
        "trust_network": list(state.trust_network),
        "post_history": list(state.post_history),
        "revision_history": list(state.revision_history),
    }


def _merge_trust(existing: tuple[str, ...], raw: object) -> tuple[str, ...]:
    seen = []
    for value in list(raw) if isinstance(raw, list) else []:
        strategy_id = str(value).strip()
        if strategy_id and strategy_id not in seen:
            seen.append(strategy_id)
    for strategy_id in existing:
        if strategy_id not in seen:
            seen.append(strategy_id)
    return tuple(seen[:TRUST_NETWORK_LIMIT])


def _append_limited(history: tuple[dict[str, object], ...], item: dict[str, object], limit: int) -> tuple[dict[str, object], ...]:
    return tuple([*history, item][-limit:])


def _social_revision_items(trace: list[dict[str, object]]) -> list[dict[str, object]]:
    items = []
    for stage in trace:
        for item in stage.get("items", []):
            if str(item.get("group", "")) != SOCIAL_GROUP or not item.get("comment"):
                continue
            items.append(item)
    return items


def _as_tuple(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    values = []
    for item in raw:
        value = str(item).strip()
        if value and value not in values:
            values.append(value)
    return tuple(values[:TRUST_NETWORK_LIMIT])


def _as_history(raw: object, limit: int) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))[-limit:]
