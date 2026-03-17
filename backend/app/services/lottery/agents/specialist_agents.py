"""Specialist LLM agents for digesting non-LLM signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ....config import Config
from ..models import PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .llm_support import (
    build_client,
    build_scores,
    dialogue_block,
    extract_rationale,
    preview_prompt,
    request_prediction,
    social_feed_block,
    validate_numbers,
)
from .prompt_blocks import (
    expert_interview_summary,
    optimization_goal,
    performance_summary,
    prompt_summary,
    single_ticket_rule,
    social_goal,
    social_memory_summary,
    world_summary,
)


GROUP = "social"
MAX_LLM_TOKENS = 1500
TRUST_LIMIT = 6
RULE_LIMIT = 8


@dataclass(frozen=True)
class SpecialistDiscussionAgent(StrategyAgent):
    """Discussion agent with a focused reading mandate."""

    specialist_mode: str

    kind: ClassVar[str] = "llm"
    uses_llm: ClassVar[bool] = True
    default_enabled: ClassVar[bool] = True
    supports_dialogue: ClassVar[bool] = True

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        if not context.peer_predictions:
            raise ValueError(f"{self.display_name} 需要先读取候选结果。")
        messages = self._build_messages(context, pick_size)
        response = request_prediction(self.display_name, context, messages, MAX_LLM_TOKENS)
        return self._to_prediction(response, context, pick_size, messages)

    def deliberate(
        self,
        context: PredictionContext,
        own_prediction: StrategyPrediction,
        peer_predictions: dict[str, dict[str, object]],
        dialogue_history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
    ) -> tuple[StrategyPrediction, dict[str, object]]:
        messages = self._build_dialogue_messages(
            context,
            own_prediction,
            peer_predictions,
            dialogue_history,
            pick_size,
            round_index,
        )
        response = request_prediction(self.display_name, context, messages, MAX_LLM_TOKENS)
        updated = self._to_prediction(response, context, pick_size, messages, dict(own_prediction.metadata or {}))
        return self._with_dialogue_note(updated, own_prediction, response, messages, peer_predictions, round_index)

    def _build_messages(self, context: PredictionContext, pick_size: int) -> list[dict[str, str]]:
        user_prompt = "\n".join(
            [
                optimization_goal(context),
                social_goal(),
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context, getattr(self, 'strategy_id', ''))}",
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                single_ticket_rule(pick_size),
                f"持续 persona / 社交状态:\n{social_memory_summary(context, self.strategy_id)}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"规则 / 非LLM结论摘要:\n{_rule_summary(context)}",
                f"当前公开讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
                self._output_schema(),
            ]
        )
        return [{"role": "system", "content": self._system_prompt(pick_size)}, {"role": "user", "content": user_prompt}]

    def _build_dialogue_messages(
        self,
        context: PredictionContext,
        own_prediction: StrategyPrediction,
        peer_predictions: dict[str, dict[str, object]],
        dialogue_history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
    ) -> list[dict[str, str]]:
        user_prompt = "\n".join(
            [
                f"讨论轮次: {round_index}",
                optimization_goal(context),
                social_goal(),
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context, getattr(self, 'strategy_id', ''))}",
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                single_ticket_rule(pick_size),
                f"持续 persona / 社交状态:\n{social_memory_summary(context, self.strategy_id)}",
                f"你当前号码: {list(own_prediction.numbers)}",
                f"你当前理由: {own_prediction.rationale}",
                f"规则 / 非LLM结论摘要:\n{_rule_summary(context)}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"你读到的公开讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
                f"其他 specialist/social 发言:\n{social_feed_block(peer_predictions, dict(context.strategy_performance))}",
                f"已有互动记录:\n{dialogue_block(dialogue_history)}",
                self._dialogue_schema(),
            ]
        )
        return [{"role": "system", "content": self._dialogue_prompt(pick_size)}, {"role": "user", "content": user_prompt}]

    def _to_prediction(
        self,
        response: dict[str, object],
        context: PredictionContext,
        pick_size: int,
        messages: list[dict[str, str]],
        base_metadata: dict[str, object] | None = None,
    ) -> StrategyPrediction:
        numbers = validate_numbers(self.display_name, response, pick_size)
        metadata = self._metadata(context, messages, response, base_metadata)
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=tuple(numbers),
            rationale=extract_rationale(self.display_name, response),
            ranked_scores=build_scores(numbers, pick_size),
            kind=self.kind,
            metadata=metadata,
        )

    def _metadata(
        self,
        context: PredictionContext,
        messages: list[dict[str, str]],
        response: dict[str, object],
        base_metadata: dict[str, object] | None,
    ) -> dict[str, object]:
        llm = build_client(context)
        metadata = dict(base_metadata or {})
        metadata.update(
            {
                "model": llm.model,
                "base_url": llm.base_url,
                "specialist_mode": self.specialist_mode,
                "focus": response.get("focus", []),
                "post": str(response.get("post", "")).strip(),
                "trusted_strategy_ids": _trusted_ids(response, context),
                "peer_strategy_ids": sorted(context.peer_predictions.keys()),
                "system_prompt": messages[0]["content"],
                "user_prompt_preview": preview_prompt(messages[1]["content"]),
                "performance_context": dict(context.strategy_performance),
                "optimization_goal": context.optimization_goal,
            }
        )
        return metadata

    def _with_dialogue_note(
        self,
        updated: StrategyPrediction,
        previous: StrategyPrediction,
        response: dict[str, object],
        messages: list[dict[str, str]],
        peer_predictions: dict[str, dict[str, object]],
        round_index: int,
    ) -> tuple[StrategyPrediction, dict[str, object]]:
        comment = str(response.get("comment", "")).strip()
        metadata = dict(updated.metadata or {})
        history = list(metadata.get("dialogue_history", []))
        history.append(
            {
                "round": round_index,
                "comment": comment,
                "numbers_before": list(previous.numbers),
                "numbers_after": list(updated.numbers),
            }
        )
        metadata["dialogue_history"] = history
        metadata["latest_dialogue_comment"] = comment
        metadata["dialogue_user_prompt_preview"] = preview_prompt(messages[1]["content"])
        revised = StrategyPrediction(**{**updated.__dict__, "metadata": metadata})
        note = {
            "round": round_index,
            "strategy_id": revised.strategy_id,
            "display_name": revised.display_name,
            "group": revised.group,
            "kind": revised.kind,
            "comment": comment,
            "numbers_before": list(previous.numbers),
            "numbers_after": list(revised.numbers),
            "peer_strategy_ids": sorted(peer_predictions.keys()),
        }
        return revised, note

    def _system_prompt(self, pick_size: int) -> str:
        return (
            "你是选号社交世界中的规则解读员。"
            "你必须先读世界记忆、专用提示词、强信号采访和公开讨论，再给出一注最终号码。"
            "你的职责是把规则/非LLM结论翻译成公共论证，而不是机械重复原始规则。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _dialogue_prompt(self, pick_size: int) -> str:
        return (
            "你正在和其他角色讨论最终选号。"
            "先引用别人，再明确你是否修正自己。"
            "保持 rule interpreter 立场，不要退化成平均主义。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _output_schema(self) -> str:
        return '只返回 JSON: {"numbers":[...], "trusted_strategy_ids":["..."], "post":"...", "rationale":"...", "focus":["..."]}'

    def _dialogue_schema(self) -> str:
        return '只返回 JSON: {"comment":"...", "numbers":[...], "trusted_strategy_ids":["..."], "rationale":"...", "focus":["..."]}'


def _rule_summary(context: PredictionContext) -> str:
    performance = dict(context.strategy_performance)
    rules = {
        strategy_id: item
        for strategy_id, item in context.peer_predictions.items()
        if str(item.get("kind", "")) != "llm"
    }
    if not rules:
        return "暂无规则 / 非LLM候选。"
    ordered = sorted(rules.items(), key=lambda item: (int(performance.get(item[0], {}).get("rank", 999)), item[0]))
    return social_feed_block({key: value for key, value in ordered[:RULE_LIMIT]}, performance)


def _trusted_ids(response: dict[str, object], context: PredictionContext) -> list[str]:
    raw = response.get("trusted_strategy_ids")
    if not isinstance(raw, list):
        return []
    valid = []
    for value in raw:
        strategy_id = str(value).strip()
        if strategy_id in context.peer_predictions and strategy_id not in valid:
            valid.append(strategy_id)
        if len(valid) >= TRUST_LIMIT:
            break
    return valid


def build_specialist_agents() -> dict[str, StrategyAgent]:
    if not Config.LLM_API_KEY:
        return {}
    agent = SpecialistDiscussionAgent(
        "rule_analyst_feed",
        "LLM-规则解读员",
        "重点阅读规则 / 非LLM结论，再把提炼后的观点带入公共讨论。",
        36,
        GROUP,
        specialist_mode="rules",
    )
    return {agent.strategy_id: agent}
