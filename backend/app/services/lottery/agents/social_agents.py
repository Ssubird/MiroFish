"""Social-style LLM agents that discuss strategy performance and candidate picks."""

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
    report_summary,
    single_ticket_rule,
    social_goal,
    social_memory_summary,
    target_summary,
    world_summary,
)


GROUP = "social"
MAX_LLM_TOKENS = 1500
TRUST_LIMIT = 6


@dataclass(frozen=True)
class SocialDiscussionAgent(StrategyAgent):
    """LLM agent that behaves like a social analyst with persistent memory."""

    social_mode: str

    kind: ClassVar[str] = "llm"
    uses_llm: ClassVar[bool] = True
    default_enabled: ClassVar[bool] = True
    supports_dialogue: ClassVar[bool] = True

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        if not context.peer_predictions:
            raise ValueError(f"{self.display_name} 需要先读取主策略候选。")
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
                target_summary(context),
                optimization_goal(context),
                social_goal(),
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context)}",
                single_ticket_rule(pick_size),
                f"持续 persona / 社交状态:\n{social_memory_summary(context, self.strategy_id)}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"外部预测/复盘报告:\n{report_summary(context)}",
                f"当前主策略讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
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
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context)}",
                single_ticket_rule(pick_size),
                f"持续 persona / 社交状态:\n{social_memory_summary(context, self.strategy_id)}",
                f"你当前发帖号码: {list(own_prediction.numbers)}",
                f"你当前发帖理由: {own_prediction.rationale}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"外部预测/复盘报告:\n{report_summary(context)}",
                f"你读到的主策略讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
                f"其他社交组发言:\n{social_feed_block(peer_predictions, dict(context.strategy_performance))}",
                f"已有互动记录:\n{dialogue_block(dialogue_history)}",
                self._dialogue_schema(),
            ]
        )
        return [
            {"role": "system", "content": self._dialogue_prompt(pick_size)},
            {"role": "user", "content": user_prompt},
        ]

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
                "social_mode": self.social_mode,
                "focus": response.get("focus", []),
                "post": str(response.get("post", "")).strip(),
                "trusted_strategy_ids": self._trusted_ids(response, context),
                "peer_strategy_ids": sorted(context.peer_predictions.keys()),
                "system_prompt": messages[0]["content"],
                "user_prompt_preview": preview_prompt(messages[1]["content"]),
                "performance_context": dict(context.strategy_performance),
                "optimization_goal": context.optimization_goal,
            }
        )
        return metadata

    def _trusted_ids(self, response: dict[str, object], context: PredictionContext) -> list[str]:
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
        metadata["dialogue_system_prompt"] = messages[0]["content"]
        metadata["dialogue_user_prompt_preview"] = preview_prompt(messages[1]["content"])
        metadata["social_peer_strategy_ids"] = sorted(peer_predictions.keys())
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
        role = (
            "你是选号讨论广场里的社交型 agent。"
            "你要阅读排行榜、命中战绩、复盘报告和他人帖子后再给观点。"
            "优先吸收近期更准、跨组更稳定的策略，但不能盲从最热共识。"
            "你只能提交一注最终号码，不能输出号码池、复式、胆拖或多方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )
        if self.social_mode == "consensus":
            return role + "你的职责是提炼讨论区里最有说服力的共识。"
        return role + "你的职责是像资深彩民一样识别拥挤与同轨风险后再做平衡。"

    def _dialogue_prompt(self, pick_size: int) -> str:
        return (
            "你正在选号讨论串里回复其他社交型 agent。"
            "先引用别人的观点，再判断是否修正自己的号码。"
            "保留高命中策略的价值，但不要机械重复最热锚点。"
            "禁止候选号码池、胆拖、复式、多方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _output_schema(self) -> str:
        return (
            '只返回 JSON: {"numbers":[...], "trusted_strategy_ids":["..."], '
            '"post":"...", "rationale":"...", "focus":["..."]}'
        )

    def _dialogue_schema(self) -> str:
        return (
            '只返回 JSON: {"comment":"...", "numbers":[...], "trusted_strategy_ids":["..."], '
            '"rationale":"...", "focus":["..."]}'
        )


def build_social_agents() -> dict[str, StrategyAgent]:
    if not Config.LLM_API_KEY:
        return {}
    agents = (
        SocialDiscussionAgent(
            "social_consensus_feed",
            "LLM-社交共识帖",
            "像讨论区置顶帖一样读取战绩榜和主策略发言，提炼高说服力共识。",
            36,
            GROUP,
            social_mode="consensus",
        ),
        SocialDiscussionAgent(
            "social_risk_feed",
            "LLM-社交分歧帖",
            "像资深彩民复盘帖一样读取战绩榜和主策略发言，主动识别拥挤与同轨风险。",
            36,
            GROUP,
            social_mode="risk",
        ),
    )
    return {agent.strategy_id: agent for agent in agents}
