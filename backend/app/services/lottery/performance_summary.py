"""Performance summaries for prompting and analysis."""

from __future__ import annotations

from .objective import objective_metrics, objective_sort_key


PROMPT_SUMMARY_LIMIT = 8
RECENT_HIT_LIMIT = 5
DEFAULT_WEIGHT = 1.0
MIN_WEIGHT = 0.25
RANK_BONUS_BASE = 0.75
TRUSTED_LIMIT = 6


def build_strategy_performance(leaderboard: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for rank, item in enumerate(leaderboard, start=1):
        issue_hits = _issue_hits(item)
        summary[str(item["strategy_id"])] = {
            "rank": rank,
            "display_name": item["display_name"],
            "group": item["group"],
            "kind": item["kind"],
            "average_hits": float(item["average_hits"]),
            "average_hit_rate": float(item["average_hit_rate"]),
            "total_hits": int(item["total_hits"]),
            "issues_scored": int(item["issues_scored"]),
            "hit_stddev": float(item["hit_stddev"]),
            "strategy_roi": float(item.get("strategy_roi", 0.0)),
            "roi_score": float(item.get("roi_score", 0.5)),
            "heat_penalty": float(item.get("heat_penalty", 0.0)),
            "objective_score": float(item.get("objective_score", 0.0)),
            "recent_hits": issue_hits[-RECENT_HIT_LIMIT:],
        }
    return summary


def rolling_strategy_performance(
    issue_results: dict[str, list[dict[str, object]]],
    strategies: dict[str, object],
    issue_index: int,
) -> dict[str, dict[str, object]]:
    leaderboard = []
    for strategy_id, strategy in strategies.items():
        previous = issue_results[strategy_id][:issue_index]
        leaderboard.append(_rolling_row(strategy_id, strategy, previous))
    ordered = sorted(leaderboard, key=objective_sort_key)
    return build_strategy_performance(ordered)


def format_performance_block(
    performance: dict[str, dict[str, object]],
    limit: int = PROMPT_SUMMARY_LIMIT,
) -> str:
    if not performance:
        return "暂无已完成回测表现；本轮只能依据历史开奖、图谱和知识片段推理。"
    lines = []
    for strategy_id, item in _ranked_rows(performance)[:limit]:
        recent = ",".join(str(value) for value in item["recent_hits"]) or "-"
        lines.append(
            f"- #{item['rank']} {item['display_name']} ({strategy_id}, {item['group']}/{item['kind']}): "
            f"objective={float(item.get('objective_score', 0.0)):.4f}, avg={float(item.get('average_hits', 0.0)):.2f}, "
            f"roi={float(item.get('strategy_roi', 0.0)):.2f}, std={float(item.get('hit_stddev', 0.0)):.2f}, recent={recent}"
        )
    return "\n".join(lines)


def performance_weight(performance: dict[str, dict[str, object]], strategy_id: str) -> float:
    item = performance.get(strategy_id)
    if not item:
        return DEFAULT_WEIGHT
    rank = max(int(item["rank"]), 1)
    objective = float(item.get("objective_score", item.get("average_hits", 0.0)))
    hit_rate = float(item.get("average_hit_rate", 0.0))
    roi_score = float(item.get("roi_score", 0.5))
    rank_bonus = RANK_BONUS_BASE / rank
    return max(objective * 2.8 + hit_rate + roi_score * 0.6 + rank_bonus + MIN_WEIGHT, MIN_WEIGHT)


def performance_rows(performance: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    return [{"strategy_id": strategy_id, **item} for strategy_id, item in _ranked_rows(performance)]


def trusted_strategy_ids(
    performance: dict[str, dict[str, object]],
    available_ids: list[str],
    limit: int = TRUSTED_LIMIT,
) -> list[str]:
    available = set(available_ids)
    rows = [strategy_id for strategy_id, _ in _ranked_rows(performance) if strategy_id in available]
    return rows[:limit]


def _ranked_rows(performance: dict[str, dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    return sorted(performance.items(), key=lambda item: int(item[1]["rank"]))


def _rolling_row(
    strategy_id: str,
    strategy: object,
    previous: list[dict[str, object]],
) -> dict[str, object]:
    metrics = objective_metrics(previous)
    return {
        "strategy_id": strategy_id,
        "display_name": strategy.display_name,
        "group": strategy.group,
        "kind": strategy.kind,
        "issue_hits": tuple(previous),
        **metrics,
    }


def _issue_hits(item: dict[str, object]) -> list[int]:
    return [int(issue["hits"]) for issue in item.get("issue_hits", [])]
