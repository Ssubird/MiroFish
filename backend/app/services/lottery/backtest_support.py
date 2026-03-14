"""Pure helpers for lottery backtest result assembly."""

from __future__ import annotations

from .constants import ALTERNATE_NUMBER_COUNT, MAX_ENSEMBLE_CONTRIBUTORS, PROCESS_PREVIEW_ISSUES
from .models import DrawRecord, StrategyPrediction
from .objective import objective_metrics, objective_policy, objective_sort_key


def build_leaderboard(
    strategies: dict[str, object],
    issue_results: dict[str, list[dict[str, object]]],
    pick_size: int,
) -> list[dict[str, object]]:
    rows = [_leaderboard_row(strategy_id, strategy, issue_results[strategy_id], pick_size) for strategy_id, strategy in strategies.items()]
    return sorted(rows, key=objective_sort_key)


def ensemble_contributors(leaderboard: list[dict[str, object]]) -> list[dict[str, object]]:
    by_group = {}
    for item in leaderboard:
        if item["group"] in by_group:
            continue
        by_group[item["group"]] = {**item, "group_rank": 1}
    contributors = list(by_group.values())
    for item in leaderboard:
        if len(contributors) >= MAX_ENSEMBLE_CONTRIBUTORS:
            break
        if any(existing["strategy_id"] == item["strategy_id"] for existing in contributors):
            continue
        group_rank = sum(existing["group"] == item["group"] for existing in contributors) + 1
        contributors.append({**item, "group_rank": group_rank})
    return sorted(contributors, key=objective_sort_key)


def build_process_trace(
    assets,
    workspace_graph,
    evaluation_draws: tuple[DrawRecord, ...],
    warmup_draws: tuple[DrawRecord, ...],
    strategies: dict[str, object],
    leaderboard: list[dict[str, object]],
    agent_dialogue_enabled: bool,
    agent_dialogue_rounds: int,
) -> list[dict[str, object]]:
    llm_count = len([item for item in strategies.values() if item.uses_llm])
    groups = ", ".join(sorted({item.group for item in strategies.values()}))
    dialogue_note = "未启用 LLM 对话"
    if agent_dialogue_enabled and llm_count > 0:
        dialogue_note = f"启用 {agent_dialogue_rounds} 轮 LLM 对话"
    return [
        {
            "step": "workspace",
            "title": "读取本地工作区",
            "status": "completed",
            "details": f"已加载 {len(assets.completed_draws)} 期已开奖数据。",
        },
        {
            "step": "graph",
            "title": "构建紫微知识图谱快照",
            "status": "completed",
            "details": _graph_step_details(workspace_graph),
            "highlights": list(workspace_graph.highlights[:8]),
        },
        {
            "step": "agents",
            "title": "编排多组 agents",
            "status": "completed",
            "details": f"启用 {len(strategies)} 个 agent，覆盖组别 {groups}，LLM {llm_count} 个；{dialogue_note}。",
        },
        _backtest_step(evaluation_draws, warmup_draws, leaderboard),
        _ensemble_step(assets),
    ]


def evaluation_summary(
    evaluation_size: int,
    warmup_size: int,
    pick_size: int,
    strategies: dict[str, object],
    llm_request_delay_ms: int,
    llm_model_name: str | None,
    llm_retry_count: int,
    llm_retry_backoff_ms: int,
    llm_parallelism: int,
    issue_parallelism: int,
    agent_dialogue_enabled: bool,
    agent_dialogue_rounds: int,
    graph_mode: str,
    zep_graph_id: str | None,
) -> dict[str, object]:
    return {
        "evaluation_size": evaluation_size,
        "warmup_size": warmup_size,
        "pick_size": pick_size,
        "llm_request_delay_ms": llm_request_delay_ms,
        "llm_model_name": llm_model_name,
        "llm_retry_count": llm_retry_count,
        "llm_retry_backoff_ms": llm_retry_backoff_ms,
        "llm_parallelism": llm_parallelism,
        "issue_parallelism": issue_parallelism,
        "agent_dialogue_enabled": agent_dialogue_enabled,
        "agent_dialogue_rounds": agent_dialogue_rounds,
        "graph_mode": graph_mode,
        "zep_graph_id": zep_graph_id,
        "selected_strategies": list(strategies.keys()),
        "selected_llm_strategies": [key for key, item in strategies.items() if item.uses_llm],
        "selected_dialogue_strategies": [
            key for key, item in strategies.items() if bool(getattr(item, "supports_dialogue", False))
        ],
        "objective_policy": objective_policy(),
    }


def dataset_summary(assets) -> dict[str, object]:
    return {
        "completed_draws": len(assets.completed_draws),
        "pending_draws": len(assets.pending_draws),
        "latest_completed_period": assets.completed_draws[-1].period,
        "pending_target_period": assets.pending_draws[-1].period if assets.pending_draws else None,
    }


def score_issue(target_draw: DrawRecord, prediction: StrategyPrediction) -> dict[str, object]:
    actual = set(target_draw.numbers)
    predicted = list(prediction.numbers)
    return {
        "period": target_draw.period,
        "date": target_draw.date,
        "hits": len(actual & set(predicted)),
        "predicted_numbers": predicted,
        "actual_numbers": list(target_draw.numbers),
        "group": prediction.group,
    }


def ensemble_numbers(breakdown: dict[int, dict[str, object]], pick_size: int) -> list[int]:
    ordered = sorted(breakdown.items(), key=lambda item: (-item[1]["score"], item[0]))
    return [number for number, _ in ordered[:pick_size]]


def alternate_numbers(breakdown: dict[int, dict[str, object]], pick_size: int) -> list[int]:
    ordered = sorted(breakdown.items(), key=lambda item: (-item[1]["score"], item[0]))
    return [number for number, _ in ordered[pick_size : pick_size + ALTERNATE_NUMBER_COUNT]]


def ensemble_breakdown(numbers: list[int], breakdown: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "number": number,
            "score": round(float(breakdown[number]["score"]), 4),
            "sources": breakdown[number]["sources"],
        }
        for number in numbers
    ]


def coordination_trace(
    seed_stages: list[tuple[str, str, dict[str, StrategyPrediction]]],
    society_rounds: list[dict[str, object]],
    final_predictions: dict[str, StrategyPrediction],
) -> list[dict[str, object]]:
    trace = [_trace_stage(stage, title, predictions) for stage, title, predictions in seed_stages if predictions]
    trace.extend(society_rounds)
    if final_predictions:
        trace.append(_trace_stage("society_final", "全场收敛结果", final_predictions))
    return trace


def attach_latest_prediction(
    leaderboard: list[dict[str, object]],
    strategy_predictions: list[dict[str, object]],
) -> list[dict[str, object]]:
    latest_by_id = {item["strategy_id"]: item for item in strategy_predictions}
    return [{**row, "latest_prediction": latest_by_id.get(row["strategy_id"])} for row in leaderboard]


def _leaderboard_row(
    strategy_id: str,
    strategy: object,
    issues: list[dict[str, object]],
    pick_size: int,
) -> dict[str, object]:
    metrics = objective_metrics(issues, pick_size)
    return {
        "strategy_id": strategy_id,
        "display_name": strategy.display_name,
        "description": strategy.description,
        "group": strategy.group,
        "required_history": strategy.required_history,
        "kind": strategy.kind,
        "uses_llm": strategy.uses_llm,
        "issue_hits": issues,
        **metrics,
    }


def _backtest_step(
    evaluation_draws: tuple[DrawRecord, ...],
    warmup_draws: tuple[DrawRecord, ...],
    leaderboard: list[dict[str, object]],
) -> dict[str, object]:
    preview = evaluation_draws[-PROCESS_PREVIEW_ISSUES:]
    warmup_text = "无预热窗口" if not warmup_draws else f"预热 {warmup_draws[0].period} 到 {warmup_draws[-1].period}"
    return {
        "step": "backtest",
        "title": "最近窗口滚动回测",
        "status": "completed",
        "details": f"{warmup_text}；计分窗口 {evaluation_draws[0].period} 到 {evaluation_draws[-1].period}。",
        "preview_periods": [draw.period for draw in preview],
        "leader": leaderboard[0]["strategy_id"] if leaderboard else None,
    }


def _ensemble_step(assets) -> dict[str, object]:
    if not assets.pending_draws:
        return {
            "step": "ensemble",
            "title": "待预测期融合",
            "status": "skipped",
            "details": "当前没有待预测期。",
        }
    return {
        "step": "ensemble",
        "title": "待预测期融合",
        "status": "completed",
        "details": f"目标期号 {assets.pending_draws[-1].period} 已生成分组融合结果。",
    }


def _graph_step_details(workspace_graph) -> str:
    provider = getattr(workspace_graph, "provider", "local")
    node_count = getattr(workspace_graph, "node_count", 0)
    edge_count = getattr(workspace_graph, "edge_count", 0)
    graph_id = getattr(workspace_graph, "backend_graph_id", None)
    if provider == "zep":
        prefix = f"使用 Zep 远程图谱 {graph_id}" if graph_id else "使用 Zep 远程图谱"
        return f"{prefix}，当前记录 {node_count} 个节点、{edge_count} 条关系。"
    if provider == "kuzu":
        return f"使用 Kuzu 本地图谱，当前记录 {node_count} 个节点、{edge_count} 条关系。"
    return f"生成 {node_count} 个节点、{edge_count} 条关系。"


def _trace_stage(stage: str, title: str, predictions: dict[str, StrategyPrediction]) -> dict[str, object]:
    return {
        "stage": stage,
        "title": title,
        "items": [_trace_prediction(prediction) for prediction in predictions.values()],
    }


def _trace_prediction(prediction: StrategyPrediction) -> dict[str, object]:
    return {
        "strategy_id": prediction.strategy_id,
        "display_name": prediction.display_name,
        "group": prediction.group,
        "kind": prediction.kind,
        "numbers": list(prediction.numbers),
        "rationale": prediction.rationale,
        "metadata": prediction.metadata or {},
        "peer_strategy_ids": list((prediction.metadata or {}).get("peer_strategy_ids", [])),
    }
