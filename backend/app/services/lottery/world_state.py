"""Persistent public-world state for lottery society simulation."""

from __future__ import annotations

from collections import Counter


ISSUE_HISTORY_LIMIT = 6
PUBLIC_POST_LIMIT = 16
INTERVIEW_HISTORY_LIMIT = 8
TREND_LIMIT = 10
WORLD_POST_GROUPS = {"social", "judge", "hybrid", "data", "metaphysics"}


class WorldStateTracker:
    """Track a shared public square across warmup, backtest, and pending prediction."""

    def __init__(self, seed: dict[str, object] | None = None):
        payload = seed or {}
        self._issue_history = _history(payload.get("issue_history"), ISSUE_HISTORY_LIMIT)
        self._public_posts = _history(payload.get("public_posts"), PUBLIC_POST_LIMIT)
        self._interview_history = _history(payload.get("interview_history"), INTERVIEW_HISTORY_LIMIT)

    def snapshot(self) -> dict[str, object]:
        return {
            "issue_history": list(self._issue_history),
            "public_posts": list(self._public_posts),
            "interview_history": list(self._interview_history),
            "trend_numbers": _trend_numbers(self._public_posts),
        }

    def record_issue(
        self,
        period: str,
        predictions: dict[str, object],
        trace: list[dict[str, object]],
        expert_interviews: tuple[dict[str, object], ...],
        actual_numbers: tuple[int, ...] | None = None,
    ) -> None:
        posts = _public_posts(period, predictions)
        self._public_posts = tuple([*self._public_posts, *posts][-PUBLIC_POST_LIMIT:])
        interviews = _interview_rows(period, expert_interviews)
        self._interview_history = tuple([*self._interview_history, *interviews][-INTERVIEW_HISTORY_LIMIT:])
        issue = _issue_summary(period, predictions, trace, actual_numbers)
        self._issue_history = tuple([*self._issue_history, issue][-ISSUE_HISTORY_LIMIT:])


def _history(raw: object, limit: int) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))[-limit:]


def _public_posts(period: str, predictions: dict[str, object]) -> list[dict[str, object]]:
    rows = []
    for prediction in predictions.values():
        if prediction.group not in WORLD_POST_GROUPS:
            continue
        metadata = dict(getattr(prediction, "metadata", {}) or {})
        rows.append(
            {
                "period": period,
                "strategy_id": prediction.strategy_id,
                "display_name": prediction.display_name,
                "group": prediction.group,
                "numbers": list(prediction.numbers),
                "trusted_strategy_ids": list(metadata.get("trusted_strategy_ids", [])),
                "message": str(metadata.get("post") or metadata.get("latest_dialogue_comment") or prediction.rationale).strip(),
            }
        )
    return rows


def _interview_rows(period: str, interviews: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    return [
        {
            "period": period,
            "source_strategy_id": item.get("source_strategy_id", "-"),
            "display_name": item.get("display_name", "-"),
            "numbers": list(item.get("numbers", [])),
            "answer": str(item.get("answer", "")).strip(),
            "report_evidence": list(item.get("report_evidence", [])),
        }
        for item in interviews
    ]


def _issue_summary(
    period: str,
    predictions: dict[str, object],
    trace: list[dict[str, object]],
    actual_numbers: tuple[int, ...] | None,
) -> dict[str, object]:
    counter = Counter(number for prediction in predictions.values() for number in prediction.numbers)
    last_stage = trace[-1] if trace else {}
    summary = {
        "period": period,
        "consensus_numbers": [number for number, _ in counter.most_common(5)],
        "top_discussed_numbers": [number for number, _ in counter.most_common(8)],
        "active_strategy_ids": list(last_stage.get("active_strategy_ids", [])) if isinstance(last_stage, dict) else [],
    }
    if actual_numbers:
        actual = set(actual_numbers)
        hits = {strategy_id: len(actual & set(prediction.numbers)) for strategy_id, prediction in predictions.items()}
        best_hits = max(hits.values(), default=0)
        summary.update(
            {
                "actual_numbers": list(actual_numbers),
                "consensus_hits": len(actual & set(summary["consensus_numbers"])),
                "best_hits": best_hits,
                "best_strategy_ids": [strategy_id for strategy_id, hit in hits.items() if hit == best_hits][:3],
            }
        )
    return summary


def _trend_numbers(posts: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    counter = Counter(number for item in posts for number in item.get("numbers", []))
    return [{"number": number, "mentions": mentions} for number, mentions in counter.most_common(TREND_LIMIT)]
