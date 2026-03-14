"""LLM-backed judge agents."""

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
    world_summary,
)


GROUP = "judge"
MAX_LLM_TOKENS = 1400


@dataclass(frozen=True)
class LLMJudgeAgent(StrategyAgent):
    """Judge agent that reads candidate threads and produces final outputs."""

    judge_mode: str

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
                f"目标期号: {context.target_draw.period}",
                optimization_goal(context),
                social_goal(),
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context)}",
                single_ticket_rule(pick_size),
                f"历史命中榜单:\n{performance_summary(context)}",
                f"外部预测/复盘报告:\n{report_summary(context)}",
                f"当前候选讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
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
                f"你的当前号码: {list(own_prediction.numbers)}",
                f"你的当前理由: {own_prediction.rationale}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"外部预测/复盘报告:\n{report_summary(context)}",
                f"主策略与社交组讨论流:\n{social_feed_block(context.peer_predictions, dict(context.strategy_performance))}",
                f"其他裁判的发言:\n{social_feed_block(peer_predictions, dict(context.strategy_performance))}",
                f"已有裁判讨论:\n{dialogue_block(dialogue_history)}",
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
                "focus": response.get("focus", []),
                "judge_mode": self.judge_mode,
                "peer_strategy_ids": sorted(context.peer_predictions.keys()),
                "system_prompt": messages[0]["content"],
                "user_prompt_preview": preview_prompt(messages[1]["content"]),
                "performance_context": dict(context.strategy_performance),
                "optimization_goal": context.optimization_goal,
                "request_delay_ms": context.llm_request_delay_ms,
                "retry_count": context.llm_retry_count,
                "retry_backoff_ms": context.llm_retry_backoff_ms,
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
        dialogue_items = list(metadata.get("dialogue_history", []))
        dialogue_items.append(
            {
                "round": round_index,
                "comment": comment,
                "numbers_before": list(previous.numbers),
                "numbers_after": list(updated.numbers),
            }
        )
        metadata["dialogue_history"] = dialogue_items
        metadata["latest_dialogue_comment"] = comment
        metadata["latest_dialogue_round"] = round_index
        metadata["judge_peer_strategy_ids"] = sorted(peer_predictions.keys())
        metadata["dialogue_system_prompt"] = messages[0]["content"]
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
        role = (
            "你是快乐8多 agent 系统里的裁判型 LLM。"
            "你只能读取候选讨论流、历史命中榜单、复盘报告和结构风险。"
            "你不能引入未来开奖结果。"
            "你只能提交一注最终号码，不能提交候选号池或多方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )
        if self.judge_mode == "consensus":
            return role + "你的职责是保留跨组高命中共识，同时压掉无效重复。"
        return role + "你的职责是压制过热、过度集中和同轴重复，同时保留命中潜力。"

    def _dialogue_prompt(self, pick_size: int) -> str:
        return (
            "你正在和其他裁判型 agent 讨论最终下注结果。"
            "先评估对方裁决，再决定是否修正自己的号码。"
            "在提高命中和控制过热之间做清晰取舍。"
            "禁止号码池、胆拖、复式、备选方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _output_schema(self) -> str:
        return '只返回 JSON: {"numbers":[...], "rationale":"...", "focus":["..."]}'

    def _dialogue_schema(self) -> str:
        return '只返回 JSON: {"comment":"...", "numbers":[...], "rationale":"...", "focus":["..."]}'


def build_judge_agents() -> dict[str, StrategyAgent]:
    if not Config.LLM_API_KEY:
        return {}
    agents = (
        LLMJudgeAgent(
            "consensus_judge",
            "LLM-裁判共识",
            "读取候选讨论流并基于跨组共识进行裁决。",
            36,
            GROUP,
            judge_mode="consensus",
        ),
        LLMJudgeAgent(
            "risk_guard_judge",
            "LLM-裁判风控",
            "读取候选讨论流并基于结构风险进行裁决。",
            36,
            GROUP,
            judge_mode="risk",
        ),
    )
    return {agent.strategy_id: agent for agent in agents}
