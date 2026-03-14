"""LLM-backed grouped lottery agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ....config import Config
from ..knowledge_context import KnowledgeContextBuilder, KnowledgeSnippet
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
    graph_summary,
    history_summary,
    optimization_goal,
    performance_summary,
    prompt_summary,
    report_summary,
    single_ticket_rule,
    social_goal,
    target_summary,
    world_summary,
)


MAX_LLM_TOKENS = 1800
DIALOGUE_SNIPPET_LIMIT = 4
GROUP_METAPHYSICS = "metaphysics"
GROUP_HYBRID = "hybrid"


@dataclass(frozen=True)
class GraphLLMAgent(StrategyAgent):
    """LLM agent that reads books, charts, graph snapshot, and reports."""

    prompt_mode: str

    kind: ClassVar[str] = "llm"
    uses_llm: ClassVar[bool] = True
    default_enabled: ClassVar[bool] = False
    supports_dialogue: ClassVar[bool] = True

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        snippets = KnowledgeContextBuilder().build(context)
        messages = self._build_messages(context, snippets, pick_size)
        response = request_prediction(self.display_name, context, messages, MAX_LLM_TOKENS)
        return self._to_prediction(response, context, pick_size, messages, snippets)

    def deliberate(
        self,
        context: PredictionContext,
        own_prediction: StrategyPrediction,
        peer_predictions: dict[str, dict[str, object]],
        dialogue_history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
    ) -> tuple[StrategyPrediction, dict[str, object]]:
        snippets = KnowledgeContextBuilder().build(context)
        messages = self._build_dialogue_messages(
            context,
            own_prediction,
            peer_predictions,
            dialogue_history,
            pick_size,
            round_index,
            snippets,
        )
        response = request_prediction(self.display_name, context, messages, MAX_LLM_TOKENS)
        updated = self._to_prediction(
            response,
            context,
            pick_size,
            messages,
            snippets,
            dict(own_prediction.metadata or {}),
        )
        return self._with_dialogue_note(updated, own_prediction, response, messages, peer_predictions, round_index)

    def _build_messages(
        self,
        context: PredictionContext,
        snippets: list[KnowledgeSnippet],
        pick_size: int,
    ) -> list[dict[str, str]]:
        user_prompt = "\n".join(
            [
                target_summary(context),
                optimization_goal(context),
                f"强信号采访纪要:\n{expert_interview_summary(context)}",
                f"世界模拟记忆:\n{world_summary(context)}",
                f"专用提示词:\n{prompt_summary(context)}",
                single_ticket_rule(pick_size),
                f"历史开奖摘要:\n{history_summary(context)}",
                f"历史命中榜单:\n{performance_summary(context)}",
                f"外部预测/复盘报告:\n{report_summary(context)}",
                f"图谱摘要:\n{graph_summary(context)}",
                f"知识片段:\n{self._snippet_block(snippets)}",
                self._output_schema(),
            ]
        )
        return [
            {"role": "system", "content": self._system_prompt(pick_size)},
            {"role": "user", "content": user_prompt},
        ]

    def _build_dialogue_messages(
        self,
        context: PredictionContext,
        own_prediction: StrategyPrediction,
        peer_predictions: dict[str, dict[str, object]],
        dialogue_history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
        snippets: list[KnowledgeSnippet],
    ) -> list[dict[str, str]]:
        user_prompt = "\n".join(
            [
                f"讨论轮次: {round_index}",
                target_summary(context),
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
                f"图谱摘要:\n{graph_summary(context)}",
                f"知识片段:\n{self._snippet_block(snippets[:DIALOGUE_SNIPPET_LIMIT])}",
                f"其他 agent 的讨论 feed:\n{social_feed_block(peer_predictions, dict(context.strategy_performance))}",
                f"已有讨论记录:\n{dialogue_block(dialogue_history)}",
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
        snippets: list[KnowledgeSnippet],
        base_metadata: dict[str, object] | None = None,
    ) -> StrategyPrediction:
        numbers = validate_numbers(self.display_name, response, pick_size)
        metadata = self._metadata(context, messages, snippets, response, base_metadata)
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
        snippets: list[KnowledgeSnippet],
        response: dict[str, object],
        base_metadata: dict[str, object] | None,
    ) -> dict[str, object]:
        llm = build_client(context)
        metadata = dict(base_metadata or {})
        metadata.update(
            {
                "model": llm.model,
                "base_url": llm.base_url,
                "sources": [snippet.source for snippet in snippets],
                "focus": response.get("focus", []),
                "graph_snapshot": context.graph_snapshot.snapshot_id,
                "graph_provider": context.graph_snapshot.provider,
                "graph_backend_id": context.graph_snapshot.backend_graph_id,
                "prompt_mode": self.prompt_mode,
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
        metadata["peer_strategy_ids"] = sorted(peer_predictions.keys())
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
        base = (
            "你是快乐8多 agent 系统里的主策略 LLM。"
            "你必须同时阅读历史开奖、图谱、命盘、知识片段、外部预测/复盘报告和历史战绩榜。"
            "你不能引用未来开奖结果。"
            "你只能提交一注最终号码，不能提交候选号池或多方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )
        if self.prompt_mode == "metaphysics":
            return base + "你的重点是玄学结构、命盘映射、图谱术语共振，并在此基础上尽量提高直接命中。"
        return base + "你的重点是融合玄学线索与统计线索，并优先提高直接命中数。"

    def _dialogue_prompt(self, pick_size: int) -> str:
        return (
            "你正在和其他选号 agent 进行讨论。"
            "讨论时不能丢掉图谱、报告、命盘和历史战绩这些全局资料。"
            "先评议别人的结论，再决定是否修正自己的号码。"
            "优先吸收历史更准、且当前跨组共识更强的有效信号。"
            "禁止输出号码池、胆拖、复式、备选方案或任何扩展集合。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _snippet_block(self, snippets: list[KnowledgeSnippet]) -> str:
        return "\n\n".join(
            f"[{snippet.kind}] {snippet.source} (score={snippet.score:.1f})\n{snippet.excerpt}"
            for snippet in snippets
        )

    def _output_schema(self) -> str:
        return '只返回 JSON: {"numbers":[...], "rationale":"...", "focus":["..."]}'

    def _dialogue_schema(self) -> str:
        return '只返回 JSON: {"comment":"...", "numbers":[...], "rationale":"...", "focus":["..."]}'


def build_llm_agents() -> dict[str, StrategyAgent]:
    if not Config.LLM_API_KEY:
        return {}
    agents = (
        GraphLLMAgent(
            "llm_ziwei_graph",
            "LLM-紫微图谱",
            "读取紫微书籍、命盘、图谱和报告后给出玄学型号码。",
            60,
            GROUP_METAPHYSICS,
            prompt_mode="metaphysics",
        ),
        GraphLLMAgent(
            "llm_hybrid_panel",
            "LLM-混合联判",
            "同时综合图谱、命盘、报告和近期统计摘要做混合选号。",
            60,
            GROUP_HYBRID,
            prompt_mode="hybrid",
        ),
    )
    return {agent.strategy_id: agent for agent in agents}
