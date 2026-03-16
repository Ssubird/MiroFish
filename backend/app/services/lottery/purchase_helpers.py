"""Helpers for purchase-plan prompts, parsing, and formatting."""

from __future__ import annotations

from .performance_summary import performance_rows
from .purchase_structures import PLAN_TYPE_PORTFOLIO, STRUCTURE_NUMBER_LIMIT


PROMPT_PREVIEW_CHARS = 900
TRUSTED_LIMIT = 6
COORDINATION_STAGE_LIMIT = 4
COORDINATION_ITEM_LIMIT = 8
SOCIAL_STATE_AGENT_LIMIT = 2


def signal_rows(predictions: dict[str, object], performance: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    ranked = {item["strategy_id"]: item for item in performance_rows(performance)}
    rows = []
    for strategy_id, prediction in predictions.items():
        metrics = ranked.get(strategy_id, {})
        rows.append(
            {
                "strategy_id": strategy_id,
                "display_name": prediction.display_name,
                "group": prediction.group,
                "kind": prediction.kind,
                "rank": metrics.get("rank"),
                "average_hits": metrics.get("average_hits", 0.0),
                "objective_score": metrics.get("objective_score", 0.0),
                "strategy_roi": metrics.get("strategy_roi", 0.0),
                "recent_hits": metrics.get("recent_hits", []),
                "numbers": list(prediction.numbers),
                "rationale": prediction.rationale,
            }
        )
    return sorted(rows, key=lambda item: (item["rank"] or 999, -float(item["objective_score"]), item["strategy_id"]))


def trusted_rows(
    predictions: dict[str, object],
    performance: dict[str, dict[str, object]],
    trusted_ids: list[str],
) -> list[dict[str, object]]:
    rows_by_id = {item["strategy_id"]: item for item in signal_rows(predictions, performance)}
    return [rows_by_id[strategy_id] for strategy_id in trusted_ids if strategy_id in rows_by_id]


def signal_block(rows: list[dict[str, object]]) -> str:
    return "\n".join(
        f"- #{row['rank'] or '-'} {row['display_name']} ({row['strategy_id']}, {row['group']}/{row['kind']}): "
        f"objective={float(row['objective_score']):.4f}, avg={float(row['average_hits']):.2f}, "
        f"roi={float(row['strategy_roi']):.2f}, recent={row['recent_hits']}, "
        f"numbers={row['numbers']} rationale={row['rationale']}"
        for row in rows[:10]
    )


def performance_block(performance: dict[str, dict[str, object]]) -> str:
    rows = performance_rows(performance)[:10]
    return "\n".join(
        f"- #{item['rank']} {item['display_name']} ({item['strategy_id']}): "
        f"objective={float(item.get('objective_score', 0.0)):.4f}, avg={float(item.get('average_hits', 0.0)):.2f}, "
        f"roi={float(item.get('strategy_roi', 0.0)):.2f}, std={float(item.get('hit_stddev', 0.0)):.2f}, "
        f"recent={item.get('recent_hits', [])}"
        for item in rows
    )


def coordination_block(trace: tuple[dict[str, object], ...] | list[dict[str, object]]) -> str:
    rows = []
    for stage in list(trace)[-COORDINATION_STAGE_LIMIT:]:
        title = stage.get("title", stage.get("stage", "-"))
        active = ", ".join(stage.get("active_strategy_ids", [])) or "-"
        rows.append(f"[{title}] active={active}")
        for item in stage.get("items", [])[:COORDINATION_ITEM_LIMIT]:
            rows.append(_coordination_line(item))
    return "\n".join(rows) or "暂无 agent 讨论记录。"


def social_state_block(state: dict[str, dict[str, object]] | object) -> str:
    if not isinstance(state, dict) or not state:
        return "暂无持久社交状态。"
    rows = []
    for strategy_id, item in list(sorted(state.items()))[:SOCIAL_STATE_AGENT_LIMIT]:
        trust = ", ".join(item.get("trust_network", [])) or "-"
        posts = item.get("post_history", [])[-1:] if isinstance(item.get("post_history"), list) else []
        post = posts[0] if posts else {}
        rows.append(
            f"- {item.get('display_name', strategy_id)} ({strategy_id}): "
            f"trust={trust}, last_post_numbers={post.get('numbers', [])}, "
            f"last_post_trust={post.get('trusted_strategy_ids', [])}"
        )
    return "\n".join(rows) or "暂无持久社交状态。"


def clean_strategy_ids(raw: object, predictions: dict[str, object]) -> list[str]:
    if not isinstance(raw, list):
        return []
    valid = []
    for value in raw:
        strategy_id = str(value).strip()
        if strategy_id in predictions and strategy_id not in valid:
            valid.append(strategy_id)
        if len(valid) >= TRUSTED_LIMIT:
            break
    return valid


def clean_numbers(raw: object, limit: int) -> list[int]:
    if not isinstance(raw, list):
        return []
    numbers = []
    for value in _normalize_number_list(raw):
        number = int(value)
        if 1 <= number <= 80 and number not in numbers:
            numbers.append(number)
        if len(numbers) >= limit:
            break
    return numbers


def clean_focus(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()][:6]


def planner_payload(
    display_name: str,
    role_id: str,
    model: str,
    messages: list[dict[str, str]],
    response: dict[str, object],
    predictions: dict[str, object],
    fallback_trusted_ids: list[str],
    pick_size: int,
) -> dict[str, object]:
    trusted_ids = clean_strategy_ids(response.get("trusted_strategy_ids"), predictions) or list(fallback_trusted_ids)
    return {
        "role_id": role_id,
        "display_name": display_name,
        "kind": "llm",
        "model": model,
        "plan_style": str(response.get("plan_style", "")).strip() or "balanced",
        "plan_type": str(response.get("plan_type", "")).strip().lower(),
        "play_size": response.get("play_size"),
        "play_size_review": _clean_text_map(response.get("play_size_review")),
        "chosen_edge": str(response.get("chosen_edge", "")).strip(),
        "trusted_strategy_ids": trusted_ids,
        "primary_ticket": clean_numbers(response.get("primary_ticket"), pick_size),
        "core_numbers": clean_numbers(response.get("core_numbers"), TRUSTED_LIMIT),
        "hedge_numbers": clean_numbers(response.get("hedge_numbers"), TRUSTED_LIMIT),
        "avoid_numbers": clean_numbers(response.get("avoid_numbers"), TRUSTED_LIMIT),
        "tickets": response.get("tickets") if isinstance(response.get("tickets"), list) else [],
        "wheel_numbers": clean_numbers(response.get("wheel_numbers"), STRUCTURE_NUMBER_LIMIT),
        "banker_numbers": clean_numbers(response.get("banker_numbers"), max(pick_size - 1, 0)),
        "drag_numbers": clean_numbers(response.get("drag_numbers"), STRUCTURE_NUMBER_LIMIT),
        "portfolio_legs": _clean_portfolio_legs(response.get("portfolio_legs"), pick_size),
        "rationale": str(response.get("rationale", "")).strip() or "LLM did not provide a purchase rationale.",
        "focus": clean_focus(response.get("focus")),
        "comment": str(response.get("comment", "")).strip(),
        "support_role_ids": _clean_role_ids(response.get("support_role_ids")),
        "system_prompt": messages[0]["content"],
        "user_prompt_preview": preview_prompt(messages[1]["content"]),
    }


def purchase_proposal_block(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No purchase proposals yet."
    return "\n".join(_proposal_line(row) for row in rows)


def purchase_dialogue_block(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No purchase discussion yet."
    return "\n".join(_discussion_line(row) for row in rows)


def preview_prompt(prompt: str) -> str:
    compact = " ".join(prompt.split())
    if len(compact) <= PROMPT_PREVIEW_CHARS:
        return compact
    return compact[:PROMPT_PREVIEW_CHARS].rstrip() + "..."


def _coordination_line(item: dict[str, object]) -> str:
    name = item.get("display_name", item.get("strategy_id", "-"))
    numbers = item.get("numbers_after", item.get("numbers", []))
    comment = str(item.get("comment", "")).strip()
    suffix = f", comment={comment}" if comment else ""
    return f"- {name}: numbers={numbers}{suffix}"


def _clean_role_ids(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    values = []
    for item in raw:
        role_id = str(item).strip()
        if role_id and role_id not in values:
            values.append(role_id)
    return values[:TRUSTED_LIMIT]


def _proposal_line(row: dict[str, object]) -> str:
    numbers = _proposal_numbers(row)
    trusted = ", ".join(row.get("trusted_strategy_ids", [])) or "-"
    return (
        f"- {row.get('display_name', row.get('role_id', '-'))} ({row.get('role_id', '-')}) "
        f"plan_type={row.get('plan_type', '-')}, play_size={row.get('play_size', '-')}, "
        f"numbers={numbers}, trusted={trusted}, "
        f"rationale={row.get('rationale', '-')}"
    )


def _discussion_line(row: dict[str, object]) -> str:
    support = ", ".join(row.get("support_role_ids", [])) or "-"
    return (
        f"- round {row.get('round', '-')} / {row.get('display_name', row.get('role_id', '-'))}: "
        f"comment={row.get('comment', '-')}, support={support}, "
        f"plan_type={row.get('plan_type', '-')}, play_size={row.get('play_size', '-')}, numbers={_proposal_numbers(row)}"
    )


def _proposal_numbers(row: dict[str, object]) -> list[int]:
    if row.get("plan_type") == PLAN_TYPE_PORTFOLIO and isinstance(row.get("portfolio_legs"), list):
        return _portfolio_numbers(row["portfolio_legs"])
    if row.get("primary_ticket"):
        return list(row["primary_ticket"])
    if row.get("wheel_numbers"):
        return list(row["wheel_numbers"])
    numbers = list(row.get("banker_numbers", []))
    numbers.extend(number for number in row.get("drag_numbers", []) if number not in numbers)
    return numbers


def _clean_portfolio_legs(raw: object, pick_size: int) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    legs = []
    for item in raw[:TRUSTED_LIMIT]:
        if not isinstance(item, dict):
            continue
        legs.append(
            {
                "plan_type": str(item.get("plan_type", "")).strip().lower(),
                "play_size": item.get("play_size"),
                "tickets": item.get("tickets") if isinstance(item.get("tickets"), list) else [],
                "wheel_numbers": clean_numbers(item.get("wheel_numbers"), STRUCTURE_NUMBER_LIMIT),
                "banker_numbers": clean_numbers(item.get("banker_numbers"), max(pick_size - 1, 0)),
                "drag_numbers": clean_numbers(item.get("drag_numbers"), STRUCTURE_NUMBER_LIMIT),
                "primary_ticket": clean_numbers(item.get("primary_ticket"), max(pick_size, 1)),
                "comment": str(item.get("comment", "")).strip(),
                "rationale": str(item.get("rationale", "")).strip(),
            }
        )
    return legs


def _clean_text_map(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value).strip() for key, value in raw.items() if str(value).strip()}


def _portfolio_numbers(legs: list[dict[str, object]]) -> list[int]:
    numbers = []
    for leg in legs:
        for value in _proposal_numbers(leg):
            if value not in numbers:
                numbers.append(value)
    return numbers


def _normalize_number_list(raw: list[object]) -> list[object]:
    if not raw:
        return raw
    if all(not isinstance(item, list) for item in raw):
        return raw
    if len(raw) == 1 and isinstance(raw[0], list):
        return raw[0]
    raise ValueError(f"LLM 返回了多层号码结构，当前只接受单注扁平数组: {raw}")
