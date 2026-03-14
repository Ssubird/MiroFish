"""Shared helpers for LLM-backed lottery agents."""

from __future__ import annotations

import re
import time

from ....utils.llm_client import LLMClient


PROMPT_PREVIEW_CHARS = 900
ERROR_PREVIEW_CHARS = 180
HISTORY_WINDOW = 8


def build_client(context) -> LLMClient:
    return LLMClient(
        model=context.llm_model_name or None,
        retry_count=context.llm_retry_count,
        retry_backoff_ms=context.llm_retry_backoff_ms,
    )


def request_prediction(display_name: str, context, messages: list[dict[str, str]], max_tokens: int) -> dict[str, object]:
    try:
        if context.llm_request_delay_ms > 0:
            time.sleep(context.llm_request_delay_ms / 1000)
        return build_client(context).chat_json(messages, temperature=0.2, max_tokens=max_tokens)
    except Exception as exc:
        raise RuntimeError(f"{display_name} 调用模型失败: {summarize_error(exc)}") from exc


def validate_numbers(display_name: str, response: dict[str, object], pick_size: int) -> list[int]:
    raw_numbers = response.get("numbers")
    if not isinstance(raw_numbers, list):
        raise ValueError(f"{display_name} 返回的 numbers 不是数组: {response}")
    numbers = [int(value) for value in raw_numbers]
    unique_numbers = list(dict.fromkeys(numbers))
    if len(unique_numbers) != pick_size:
        raise ValueError(f"{display_name} 返回号码数量不等于 {pick_size}: {unique_numbers}")
    if any(number < 1 or number > 80 for number in unique_numbers):
        raise ValueError(f"{display_name} 返回了越界号码: {unique_numbers}")
    return unique_numbers


def extract_rationale(display_name: str, response: dict[str, object]) -> str:
    rationale = str(response.get("rationale", "")).strip()
    if rationale:
        return rationale
    raise ValueError(f"{display_name} 返回了空的 rationale")


def build_scores(numbers: list[int], pick_size: int) -> tuple[tuple[int, float], ...]:
    return tuple((number, float(pick_size - index)) for index, number in enumerate(numbers))


def preview_prompt(prompt: str) -> str:
    compact = " ".join(prompt.split())
    if len(compact) <= PROMPT_PREVIEW_CHARS:
        return compact
    return compact[:PROMPT_PREVIEW_CHARS].rstrip() + "..."


def peer_block(predictions: dict[str, dict[str, object]]) -> str:
    if not predictions:
        return "暂无。"
    ordered = sorted(predictions.items())
    return "\n".join(_peer_line(strategy_id, item) for strategy_id, item in ordered)


def social_feed_block(
    predictions: dict[str, dict[str, object]],
    performance: dict[str, dict[str, object]] | None = None,
) -> str:
    if not predictions:
        return "暂无。"
    metrics = performance or {}
    ordered = sorted(predictions.items(), key=lambda item: _peer_sort_key(item[0], metrics))
    return "\n".join(_social_feed_line(strategy_id, item, metrics) for strategy_id, item in ordered)


def dialogue_block(dialogue_history: tuple[dict[str, object], ...]) -> str:
    if not dialogue_history:
        return "暂无。"
    return "\n".join(_dialogue_line(item) for item in dialogue_history[-HISTORY_WINDOW:])


def summarize_error(exc: Exception) -> str:
    content = re.sub(r"<[^>]+>", " ", str(exc))
    summary = " ".join(content.split())
    if len(summary) > ERROR_PREVIEW_CHARS:
        summary = summary[:ERROR_PREVIEW_CHARS].rstrip() + "..."
    return f"{type(exc).__name__}: {summary}"


def _peer_line(strategy_id: str, item: dict[str, object]) -> str:
    return (
        f"- {strategy_id} / {item.get('display_name', strategy_id)} / {item.get('group', '')}: "
        f"numbers={item.get('numbers', [])} rationale={item.get('rationale', '')}"
    )


def _peer_sort_key(strategy_id: str, performance: dict[str, dict[str, object]]) -> tuple[int, float, str]:
    item = performance.get(strategy_id, {})
    return (
        int(item.get("rank", 999)),
        -float(item.get("objective_score", 0.0)),
        strategy_id,
    )


def _social_feed_line(
    strategy_id: str,
    item: dict[str, object],
    performance: dict[str, dict[str, object]],
) -> str:
    trusted = _trusted_ids(item)
    trusted_text = f"\n  信任对象: {', '.join(trusted)}" if trusted else ""
    return (
        f"- @{strategy_id} | {item.get('display_name', strategy_id)} | "
        f"{item.get('group', '')}/{item.get('kind', '')} | {_performance_badge(performance.get(strategy_id))}\n"
        f"  发帖号码: {item.get('numbers', [])}\n"
        f"  观点摘要: {item.get('rationale', '')}{trusted_text}"
    )


def _performance_badge(metrics: dict[str, object] | None) -> str:
    if not metrics:
        return "未形成历史战绩"
    recent = ",".join(str(value) for value in metrics.get("recent_hits", [])) or "-"
    return (
        f"rank=#{metrics.get('rank', '-')}, "
        f"objective={float(metrics.get('objective_score', 0.0)):.4f}, "
        f"avg={float(metrics.get('average_hits', 0.0)):.2f}, "
        f"roi={float(metrics.get('strategy_roi', 0.0)):.2f}, "
        f"total={int(metrics.get('total_hits', 0))}, "
        f"recent={recent}"
    )


def _trusted_ids(item: dict[str, object]) -> list[str]:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("trusted_strategy_ids")
    if not isinstance(raw, list):
        return []
    return [str(value) for value in raw if str(value).strip()]


def _dialogue_line(item: dict[str, object]) -> str:
    return (
        f"- round {item.get('round')} / {item.get('strategy_id')}: "
        f"comment={item.get('comment', '')} after={item.get('numbers_after', [])}"
    )
