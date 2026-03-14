"""Base interfaces for lottery strategy agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from ..models import PredictionContext, StrategyPrediction


@dataclass(frozen=True)
class StrategyAgent(ABC):
    """Immutable strategy contract used by all lottery agent groups."""

    strategy_id: str
    display_name: str
    description: str
    required_history: int
    group: str

    kind: ClassVar[str] = "rule"
    uses_llm: ClassVar[bool] = False
    default_enabled: ClassVar[bool] = True
    supports_dialogue: ClassVar[bool] = False

    @abstractmethod
    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        """Generate a prediction from an isolated context."""

    def ensure_history(self, context: PredictionContext) -> None:
        history_count = len(context.history_draws)
        if history_count >= self.required_history:
            return
        raise ValueError(
            f"{self.display_name} 需要至少 {self.required_history} 期历史数据，"
            f"当前只有 {history_count} 期。"
        )
