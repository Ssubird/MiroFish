"""Full-context LLM agent that injects the complete prompt.md and keno8 predict data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ....config import Config
from ..models import PredictionContext, StrategyPrediction
from .base import StrategyAgent
from .llm_support import (
    build_scores,
    extract_rationale,
    preview_prompt,
    request_prediction,
    validate_numbers,
)


GROUP = "metaphysics"
MAX_LLM_TOKENS = 4000
DATA_WINDOW = 120
ZIWEIDOUSHU_ROOT = Path(__file__).resolve().parents[5] / "ziweidoushu"
PROMPT_PATH = ZIWEIDOUSHU_ROOT / "knowledge" / "prompts" / "prompt.md"
DATA_PATH = ZIWEIDOUSHU_ROOT / "data" / "draws" / "keno8_predict_data.json"


def _read_prompt_file() -> str:
    if not PROMPT_PATH.exists():
        return "(prompt.md not found)"
    return PROMPT_PATH.read_text(encoding="utf-8")


def _read_predict_data(window: int) -> str:
    """Read the last *window* periods from keno8_predict_data.json.

    The file can be very large (1MB+), so we only keep the tail
    to stay within LLM context limits.
    """
    if not DATA_PATH.exists():
        return "(keno8_predict_data.json not found)"
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return "(unexpected data format)"
    segment = raw[-window:]
    return json.dumps(segment, ensure_ascii=False, indent=1)


@dataclass(frozen=True)
class FullContextAgent(StrategyAgent):
    """LLM agent whose prompt consists entirely of prompt.md + keno8 data."""

    data_window: int

    kind: ClassVar[str] = "llm"
    uses_llm: ClassVar[bool] = True
    default_enabled: ClassVar[bool] = False
    supports_dialogue: ClassVar[bool] = False

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        self.ensure_history(context)
        messages = self._build_messages(pick_size)
        response = request_prediction(self.display_name, context, messages, MAX_LLM_TOKENS)
        return self._to_prediction(response, pick_size, messages)

    def _build_messages(self, pick_size: int) -> list[dict[str, str]]:
        prompt_text = _read_prompt_file()
        data_text = _read_predict_data(self.data_window)
        user_prompt = "\n\n".join([
            "=== 提示词 (prompt.md) ===",
            prompt_text,
            f"=== 命盘+历史数据 (最近 {self.data_window} 期 from keno8_predict_data.json) ===",
            data_text,
            self._output_rule(pick_size),
        ])
        return [
            {"role": "system", "content": self._system_prompt(pick_size)},
            {"role": "user", "content": user_prompt},
        ]

    def _to_prediction(
        self,
        response: dict[str, object],
        pick_size: int,
        messages: list[dict[str, str]],
    ) -> StrategyPrediction:
        numbers = validate_numbers(self.display_name, response, pick_size)
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=tuple(numbers),
            rationale=extract_rationale(self.display_name, response),
            ranked_scores=build_scores(numbers, pick_size),
            kind=self.kind,
            metadata={
                "prompt_path": str(PROMPT_PATH),
                "data_path": str(DATA_PATH),
                "data_window": self.data_window,
                "system_prompt": messages[0]["content"],
                "user_prompt_preview": preview_prompt(messages[1]["content"]),
            },
        )

    def _system_prompt(self, pick_size: int) -> str:
        return (
            "你是紫微斗数快乐8选号专家。"
            "你必须严格按照 prompt.md 中的思维流程来分析命盘数据。"
            "结合历史数据中的命盘、干支、四化和开奖号码，预测最新一期（没有开奖号码的那期）。"
            "你不能引用未来开奖结果，只能基于已开奖数据进行推演。"
            "你只能提交一注最终号码，不能提交候选号池或多方案。"
            f"numbers 必须是 {pick_size} 个 1-80 的不重复整数。"
        )

    def _output_rule(self, pick_size: int) -> str:
        return (
            f"请预测最新一期（最后一条没有 numbers 或 numbers 为空的记录）的开奖号码。\n"
            f"必须选出 {pick_size} 个 1-80 的不重复整数。\n"
            '只返回 JSON: {"numbers":[...], "rationale":"...", "focus":["..."]}'
        )


def build_full_context_agents() -> dict[str, StrategyAgent]:
    if not Config.LLM_API_KEY:
        return {}
    agent = FullContextAgent(
        "full_context_ziwei",
        "全量紫微专判",
        "完整注入 prompt.md 和命盘数据，独立进行紫微斗数分析选号。",
        DATA_WINDOW,
        GROUP,
        data_window=DATA_WINDOW,
    )
    return {agent.strategy_id: agent}
