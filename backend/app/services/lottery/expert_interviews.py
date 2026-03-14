"""Interview-style briefs for top lottery strategies."""

from __future__ import annotations

from .models import StrategyPrediction


INTERVIEW_LIMIT = 3
REPORT_LINE_LIMIT = 2
REPORT_LINE_CHARS = 160
RATIONALE_CHARS = 220
RULE_FIRST_GROUPS = {"data", "hybrid"}


def build_expert_interviews(context, predictions: dict[str, StrategyPrediction]) -> tuple[dict[str, object], ...]:
    rows = _candidate_rows(context, predictions)
    return tuple(_interview_brief(context, prediction, metrics) for prediction, metrics in rows[:INTERVIEW_LIMIT])


def _candidate_rows(context, predictions: dict[str, StrategyPrediction]) -> list[tuple[StrategyPrediction, dict[str, object]]]:
    rows = []
    for strategy_id, prediction in predictions.items():
        metrics = dict(context.strategy_performance.get(strategy_id, {}))
        if metrics:
            rows.append((prediction, metrics))
    return sorted(rows, key=lambda item: _candidate_key(item[0], item[1]))


def _candidate_key(prediction: StrategyPrediction, metrics: dict[str, object]) -> tuple[int, int, int, float, str]:
    return (
        0 if prediction.kind == "rule" else 1,
        0 if prediction.group in RULE_FIRST_GROUPS else 1,
        int(metrics.get("rank", 999) or 999),
        -float(metrics.get("objective_score", 0.0)),
        prediction.strategy_id,
    )


def _interview_brief(context, prediction: StrategyPrediction, metrics: dict[str, object]) -> dict[str, object]:
    recent = list(metrics.get("recent_hits", []))
    return {
        "source_strategy_id": prediction.strategy_id,
        "display_name": prediction.display_name,
        "group": prediction.group,
        "kind": prediction.kind,
        "rank": int(metrics.get("rank", 999) or 999),
        "objective_score": round(float(metrics.get("objective_score", 0.0)), 4),
        "average_hits": round(float(metrics.get("average_hits", 0.0)), 4),
        "strategy_roi": round(float(metrics.get("strategy_roi", 0.0)), 4),
        "recent_hits": recent,
        "numbers": list(prediction.numbers),
        "answer": _interview_answer(prediction, metrics, recent),
        "report_evidence": _report_evidence(context, prediction.strategy_id),
    }


def _interview_answer(
    prediction: StrategyPrediction,
    metrics: dict[str, object],
    recent_hits: list[int],
) -> str:
    recent = ",".join(str(value) for value in recent_hits) or "-"
    rationale = _compact(prediction.rationale, RATIONALE_CHARS)
    return (
        f"rank=#{int(metrics.get('rank', 999) or 999)}, "
        f"objective={float(metrics.get('objective_score', 0.0)):.4f}, "
        f"avg={float(metrics.get('average_hits', 0.0)):.2f}, "
        f"roi={float(metrics.get('strategy_roi', 0.0)):.2f}, recent={recent}; "
        f"本期主张保留 {list(prediction.numbers)}。核心理由: {rationale}"
    )


def _report_evidence(context, strategy_id: str) -> list[str]:
    evidence = []
    needle = strategy_id.lower()
    for document in context.knowledge_documents:
        if document.kind != "report":
            continue
        for line in document.content.splitlines():
            compact = " ".join(line.split())
            if not compact or compact.startswith(("说明", "提示", "|")):
                continue
            if needle not in compact.lower():
                continue
            if compact not in evidence:
                evidence.append(_compact(compact, REPORT_LINE_CHARS))
            if len(evidence) >= REPORT_LINE_LIMIT:
                return evidence
    return evidence


def _compact(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
