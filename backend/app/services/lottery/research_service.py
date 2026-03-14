"""Lottery research orchestration service."""

from __future__ import annotations

from .backtest_policy import (
    judge_strategies,
    primary_strategies,
    select_strategies,
    validate_dataset,
    validate_request,
)
from .constants import (
    DEFAULT_AGENT_DIALOGUE_ENABLED,
    DEFAULT_AGENT_DIALOGUE_ROUNDS,
    DEFAULT_EVALUATION_SIZE,
    DEFAULT_ISSUE_PARALLELISM,
    DEFAULT_LLM_PARALLELISM,
    DEFAULT_LLM_RETRY_BACKOFF_MS,
    DEFAULT_LLM_RETRY_COUNT,
    DEFAULT_PICK_SIZE,
    JUDGE_GROUP,
    LOCAL_GRAPH_MODE,
    PRIMARY_GROUPS,
    WORLD_WARMUP_ISSUES,
)
from .graph_context import DomainGraphService
from .kuzu_graph import KuzuGraphService
from .paths import DRAW_DATA_FILE, LOTTERY_ROOT
from .report_writer import LotteryReportWriter
from .repository import LotteryDataRepository
from .research_runtime import LotteryResearchRuntime
from .research_types import LLMRunOptions
from .serializers import (
    serialize_chart,
    serialize_document,
    serialize_draw_head,
    serialize_graph,
    serialize_optional_draw,
    serialize_strategy,
    summarize_charts,
    summarize_documents,
)
from .deliberation import DialogueCoordinator
from .document_filters import grounding_documents
from .zep_graph import ZepGraphService
from .catalog import build_llm_status, build_strategy_group_summary


class LotteryResearchService:
    """Build overview data and execute rolling backtests."""

    def __init__(
        self,
        repository: LotteryDataRepository | None = None,
        graph_service: DomainGraphService | None = None,
        dialogue_coordinator: DialogueCoordinator | None = None,
        zep_graph_service: ZepGraphService | None = None,
        kuzu_graph_service: KuzuGraphService | None = None,
        report_writer: LotteryReportWriter | None = None,
    ):
        runtime = LotteryResearchRuntime(
            repository or LotteryDataRepository(),
            graph_service or DomainGraphService(),
            dialogue_coordinator or DialogueCoordinator(),
            zep_graph_service or ZepGraphService(),
            kuzu_graph_service or KuzuGraphService(),
        )
        self.runtime = runtime
        self.kuzu_graph_service = runtime.kuzu_graph_service
        self.zep_graph_service = runtime.zep_graph_service
        self.report_writer = report_writer or LotteryReportWriter()

    def build_overview(self) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        return {
            "workspace_root": str(LOTTERY_ROOT),
            "draw_file": str(DRAW_DATA_FILE),
            "completed_draws": len(assets.completed_draws),
            "pending_draws": len(assets.pending_draws),
            "document_summary": summarize_documents(assets.knowledge_documents),
            "chart_summary": summarize_charts(assets.chart_profiles),
            "workspace_graph": serialize_graph(assets.local_workspace_graph),
            "kuzu_graph_status": assets.kuzu_graph_status,
            "zep_graph_status": assets.zep_graph_status,
            "strategy_group_summary": build_strategy_group_summary(assets.strategies),
            "llm_status": build_llm_status(),
            "latest_completed_draw": serialize_draw_head(assets.completed_draws[-1]),
            "pending_target_draw": serialize_optional_draw(assets.pending_draws),
            "knowledge_documents": [serialize_document(item) for item in assets.knowledge_documents],
            "chart_profiles": [serialize_chart(item) for item in assets.chart_profiles],
            "available_strategies": [serialize_strategy(item) for item in assets.strategies.values()],
        }

    def sync_zep_graph(self, force: bool = False) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        target_draw = assets.pending_draws[-1] if assets.pending_draws else None
        return self.zep_graph_service.sync_workspace(
            grounding_documents(assets.knowledge_documents, target_draw),
            assets.chart_profiles,
            assets.completed_draws,
            assets.pending_draws,
            force,
        )

    def sync_kuzu_graph(self, force: bool = False) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        target_draw = assets.pending_draws[-1] if assets.pending_draws else None
        return self.kuzu_graph_service.sync_workspace(
            grounding_documents(assets.knowledge_documents, target_draw),
            assets.chart_profiles,
            assets.completed_draws,
            assets.pending_draws,
            force,
        )

    def run_backtest(
        self,
        evaluation_size: int = DEFAULT_EVALUATION_SIZE,
        pick_size: int = DEFAULT_PICK_SIZE,
        strategy_ids: list[str] | None = None,
        llm_request_delay_ms: int = 0,
        llm_model_name: str | None = None,
        llm_retry_count: int = DEFAULT_LLM_RETRY_COUNT,
        llm_retry_backoff_ms: int = DEFAULT_LLM_RETRY_BACKOFF_MS,
        llm_parallelism: int = DEFAULT_LLM_PARALLELISM,
        issue_parallelism: int = DEFAULT_ISSUE_PARALLELISM,
        agent_dialogue_enabled: bool = DEFAULT_AGENT_DIALOGUE_ENABLED,
        agent_dialogue_rounds: int = DEFAULT_AGENT_DIALOGUE_ROUNDS,
        graph_mode: str = LOCAL_GRAPH_MODE,
        zep_graph_id: str | None = None,
    ) -> dict[str, object]:
        options = self._build_options(
            evaluation_size,
            pick_size,
            llm_request_delay_ms,
            llm_model_name,
            llm_retry_count,
            llm_retry_backoff_ms,
            llm_parallelism,
            issue_parallelism,
            agent_dialogue_enabled,
            agent_dialogue_rounds,
            graph_mode,
            zep_graph_id,
        )
        assets = self.runtime.load_workspace()
        selected = select_strategies(assets.strategies, strategy_ids)
        validate_dataset(
            assets,
            evaluation_size,
            WORLD_WARMUP_ISSUES,
            selected,
            primary_strategies(selected, PRIMARY_GROUPS),
            judge_strategies(selected, JUDGE_GROUP),
        )
        payload = self.runtime.result_payload(assets, selected, evaluation_size, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        return payload

    def _build_options(
        self,
        evaluation_size: int,
        pick_size: int,
        delay: int,
        model: str | None,
        retry_count: int,
        retry_backoff: int,
        parallelism: int,
        issue_parallelism: int,
        dialogue_enabled: bool,
        dialogue_rounds: int,
        graph_mode: str,
        zep_graph_id: str | None,
    ) -> LLMRunOptions:
        validate_request(
            evaluation_size,
            pick_size,
            delay,
            retry_count,
            retry_backoff,
            parallelism,
            issue_parallelism,
            dialogue_rounds,
            graph_mode,
        )
        return LLMRunOptions(
            delay,
            model,
            retry_count,
            retry_backoff,
            parallelism,
            issue_parallelism,
            dialogue_enabled,
            dialogue_rounds,
            graph_mode,
            zep_graph_id,
        )
