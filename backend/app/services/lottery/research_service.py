"""Lottery research orchestration service."""

from __future__ import annotations

from dataclasses import replace
import inspect
import os

from ...config import Config, reload_project_env
from .backtest_policy import (
    judge_strategies,
    primary_strategies,
    select_strategies,
    validate_dataset,
    validate_request,
)
from .constants import (
    WORLD_V2_MARKET_RUNTIME_MODE,
    DEFAULT_AGENT_DIALOGUE_ENABLED,
    DEFAULT_AGENT_DIALOGUE_ROUNDS,
    DEFAULT_BUDGET_YUAN,
    DEFAULT_EVALUATION_SIZE,
    DEFAULT_ISSUE_PARALLELISM,
    DEFAULT_LLM_PARALLELISM,
    DEFAULT_LIVE_INTERVIEW_ENABLED,
    DEFAULT_LLM_RETRY_BACKOFF_MS,
    DEFAULT_LLM_RETRY_COUNT,
    DEFAULT_PICK_SIZE,
    JUDGE_GROUP,
    LEGACY_RUNTIME_MODE,
    LOCAL_GRAPH_MODE,
    PRIMARY_GROUPS,
    WORLD_V1_RUNTIME_MODE,
    WORLD_WARMUP_ISSUES,
)
from .agent_fabric_registry import AgentFabricRegistry
from .agent_fabric_snapshot import write_agent_fabric_snapshot
from .graph_context import DomainGraphService
from .kuzu_graph import KuzuGraphService
from .paths import DRAW_DATA_FILE, LOTTERY_ROOT
from .report_writer import LotteryReportWriter
from .repository import LotteryDataRepository
from .research_runtime import LotteryResearchRuntime
from .research_types import LLMRunOptions, WorkspaceAssets
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
from .document_filters import grounding_documents, prompt_documents
from .execution_registry import ExecutionRegistry
from .letta_no_mcp_client import LettaNoMcpClient
from .local_world_client import LocalWorldClient
from .world_runtime import LotteryWorldRuntime
from .world_runtime_backend import (
    NO_MCP_BACKEND_LETTA,
    NO_MCP_BACKEND_LOCAL,
    world_v2_no_mcp_backend,
)
from .world_runtime_readiness import ensure_runtime_ready, runtime_readiness
from .world_runtime_flags import allow_world_v2_without_mcp
from .world_v2_runtime import LotteryWorldV2Runtime
from .zep_graph import ZepGraphService
from .catalog import build_llm_status, build_strategy_group_summary
from .catalog import build_market_v2_catalog


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
        world_runtime: LotteryWorldRuntime | None = None,
    ):
        runtime = LotteryResearchRuntime(
            repository or LotteryDataRepository(),
            graph_service or DomainGraphService(),
            dialogue_coordinator or DialogueCoordinator(),
            zep_graph_service or ZepGraphService(),
            kuzu_graph_service or KuzuGraphService(),
        )
        self.runtime = runtime
        self.world_runtime = world_runtime or LotteryWorldRuntime(
            runtime.graph_service,
            kuzu_graph_service=runtime.kuzu_graph_service,
        )
        self.execution_registry = ExecutionRegistry()
        world_v2_client = getattr(self.world_runtime, "letta_client", None)
        if world_v2_client is None:
            world_v2_client = _world_v2_no_mcp_client(self.execution_registry)
        self.world_v2_runtime = LotteryWorldV2Runtime(
            runtime.graph_service,
            store=self.world_runtime.store,
            letta_client=world_v2_client,
            kuzu_graph_service=runtime.kuzu_graph_service,
            execution_registry=self.execution_registry,
        )
        self.kuzu_graph_service = runtime.kuzu_graph_service
        self.zep_graph_service = runtime.zep_graph_service
        self.report_writer = report_writer or LotteryReportWriter()

    def _runtime_for_mode(self, runtime_mode: str):
        if runtime_mode == WORLD_V2_MARKET_RUNTIME_MODE:
            return self.world_v2_runtime
        return self.world_runtime

    def _current_runtime(self):
        session_id = self.world_runtime.store.current_session_id()
        if not session_id:
            return self.world_v2_runtime
        return self._runtime_for_session(session_id)

    def _runtime_for_session(self, session_id: str):
        session = self.world_runtime.store.load_session(session_id)
        if session.get("runtime_mode") == WORLD_V2_MARKET_RUNTIME_MODE:
            return self.world_v2_runtime
        return self.world_runtime

    def build_overview(self) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        history_periods = [d.period for d in reversed(assets.completed_draws[-50:])] if assets.completed_draws else []
        return {
            "workspace_root": str(LOTTERY_ROOT),
            "draw_file": str(DRAW_DATA_FILE),
            "completed_draws": len(assets.completed_draws),
            "pending_draws": len(assets.pending_draws),
            "history_periods": history_periods,
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

    def get_execution_registry(self) -> dict[str, object]:
        return self.execution_registry.export_catalog()

    def get_agent_fabric_registry(self) -> dict[str, object]:
        assets = self.runtime.load_workspace()
        registry = AgentFabricRegistry(execution_registry=self.execution_registry)
        snapshot = write_agent_fabric_snapshot(registry, assets, self.execution_registry)
        return {
            "registry": snapshot["payload"],
            "snapshot_artifacts": {
                "json_path": snapshot["json_path"],
                "markdown_path": snapshot["markdown_path"],
            },
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
        graph_docs = [
            *grounding_documents(assets.knowledge_documents, target_draw),
            *prompt_documents(assets.knowledge_documents),
        ]
        return self.kuzu_graph_service.sync_workspace(
            graph_docs,
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
        runtime_mode: str = Config.LOTTERY_RUNTIME_MODE,
        warmup_size: int = WORLD_WARMUP_ISSUES,
        live_interview_enabled: bool = DEFAULT_LIVE_INTERVIEW_ENABLED,
        budget_yuan: int = DEFAULT_BUDGET_YUAN,
        session_id: str | None = None,
        execution_overrides: dict[str, object] | None = None,
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
            runtime_mode,
            warmup_size,
            live_interview_enabled,
            budget_yuan,
            session_id,
            execution_overrides,
        )
        assets = self.runtime.load_workspace()
        self._ensure_world_v2_kuzu_synced(runtime_mode, assets)
        selected = select_strategies(assets.strategies, strategy_ids)
        if runtime_mode == LEGACY_RUNTIME_MODE:
            validate_dataset(
                assets,
                evaluation_size,
                warmup_size,
                selected,
                primary_strategies(selected, PRIMARY_GROUPS),
                judge_strategies(selected, JUDGE_GROUP),
            )
            payload = self.runtime.result_payload(assets, selected, evaluation_size, pick_size, options)
        else:
            rt = self._runtime_for_mode(runtime_mode)
            payload = rt.run_backtest(assets, selected, evaluation_size, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        if runtime_mode in (WORLD_V1_RUNTIME_MODE, WORLD_V2_MARKET_RUNTIME_MODE):
            rt = self._runtime_for_mode(runtime_mode)
            rt.store.save_result(payload["world_session"]["session_id"], payload)
            rt.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload

    def start_world_session(self, **kwargs) -> dict[str, object]:
        runtime_mode = str(kwargs.get("runtime_mode") or WORLD_V2_MARKET_RUNTIME_MODE).strip()
        self.ensure_world_runtime_ready(runtime_mode)
        return self.advance_world_session(**{**kwargs, "runtime_mode": runtime_mode})

    def advance_world_session(
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
        runtime_mode: str = WORLD_V2_MARKET_RUNTIME_MODE,
        warmup_size: int = WORLD_WARMUP_ISSUES,
        live_interview_enabled: bool = DEFAULT_LIVE_INTERVIEW_ENABLED,
        budget_yuan: int = DEFAULT_BUDGET_YUAN,
        session_id: str | None = None,
        assets: WorkspaceAssets | None = None,
        visible_through_period: str | None = None,
        execution_overrides: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del evaluation_size
        self.ensure_world_runtime_ready(runtime_mode)
        visible_through_period = _optional_string(visible_through_period)
        full_assets = self.runtime.load_workspace()
        self._ensure_world_v2_kuzu_synced(runtime_mode, full_assets)
        options = self._build_options(
            DEFAULT_EVALUATION_SIZE,
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
            runtime_mode,
            warmup_size,
            live_interview_enabled,
            budget_yuan,
            session_id,
            execution_overrides,
        )
        if assets is None:
            assets = self._assets_for_visible_through_period(
                full_assets,
                visible_through_period,
            )

        selected = self._selected_world_strategies(assets, strategy_ids, runtime_mode)
        rt = self._runtime_for_mode(runtime_mode)
        payload = rt.advance(assets, selected, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        rt.store.save_result(payload["world_session"]["session_id"], payload)
        rt.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload

    def prepare_world_session(
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
        runtime_mode: str = WORLD_V2_MARKET_RUNTIME_MODE,
        warmup_size: int = WORLD_WARMUP_ISSUES,
        live_interview_enabled: bool = DEFAULT_LIVE_INTERVIEW_ENABLED,
        budget_yuan: int = DEFAULT_BUDGET_YUAN,
        session_id: str | None = None,
        visible_through_period: str | None = None,
        execution_overrides: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if runtime_mode not in (WORLD_V1_RUNTIME_MODE, WORLD_V2_MARKET_RUNTIME_MODE):
            raise ValueError(f"prepare_world_session unsupported mode: {runtime_mode}")
        self.ensure_world_runtime_ready(runtime_mode)
        visible_through_period = _optional_string(visible_through_period)
        full_assets = self.runtime.load_workspace()
        self._ensure_world_v2_kuzu_synced(runtime_mode, full_assets)
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
            runtime_mode,
            warmup_size,
            live_interview_enabled,
            budget_yuan,
            session_id,
            execution_overrides,
        )
        assets = self._assets_for_visible_through_period(
            full_assets,
            visible_through_period,
        )
        selected = self._selected_world_strategies(assets, strategy_ids, runtime_mode)
        rt = self._runtime_for_mode(runtime_mode)
        session = rt.prepare_session(
            assets,
            selected,
            pick_size,
            options.model_name,
            options.session_id,
            options.execution_overrides,
        )
        return {
            "evaluation": {
                "runtime_mode": runtime_mode,
                "world_mode": "persistent",
                "pick_size": pick_size,
                "graph_mode": "embedded_world_context",
                "llm_model_name": options.model_name,
                "llm_parallelism": llm_parallelism,
                "issue_parallelism": issue_parallelism,
                "live_interview_enabled": live_interview_enabled,
                "budget_yuan": budget_yuan,
            },
            "world_session": {
                "session_id": session["session_id"],
                "status": session["status"],
                "budget_yuan": session.get("budget_yuan"),
                "current_phase": session["current_phase"],
                "current_period": session.get("current_period"),
                "llm_model_name": session.get("llm_model_name"),
                "game_id": session.get("game_id", "happy8"),
                "active_agent_ids": session.get("active_agent_ids", []),
                "shared_memory": session["shared_memory"],
                "agents": session["agents"],
                "execution_overrides_snapshot": session.get("execution_overrides", {}),
                "resolved_execution_bindings": session.get("resolved_execution_bindings", {}),
                "asset_manifest": session.get("asset_manifest", []),
            },
        }

    def get_world_session(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_session(session_id)

    def get_current_world_session(self) -> dict[str, object]:
        return self._current_runtime().get_current_session()

    def reset_current_world_session(self) -> dict[str, object]:
        self.world_runtime.store.reset_current_session()
        return {"status": "reset", "current_session_id": None}

    def get_world_timeline(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 50,
        latest: bool = False,
    ) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_timeline(session_id, offset, limit, latest)

    def interview_world_agent(self, session_id: str, agent_id: str, prompt: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).interview_agent(session_id, agent_id, prompt, self.runtime.load_workspace())

    def get_world_result(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_result(session_id)

    def get_world_graph(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_graph(session_id)

    def get_recent_draw_stats(self, session_id: str | None = None) -> dict[str, object]:
        if session_id is None:
            session_id = self.world_runtime.store.current_session_id()
        if session_id is None:
            return self._current_runtime().get_recent_draw_stats(self.runtime.load_workspace(), None)
        return self._runtime_for_session(session_id).get_recent_draw_stats(self.runtime.load_workspace(), session_id)

    def finalize_world_result(self, session_id: str) -> dict[str, object]:
        payload = self.get_world_result(session_id)
        if payload.get("report_artifacts"):
            return payload
        payload["report_artifacts"] = self.report_writer.write(payload)
        rt = self._runtime_for_session(session_id)
        rt.attach_report_artifacts(session_id, payload["report_artifacts"])
        rt.store.save_result(session_id, payload)
        return payload

    def get_world_runtime_readiness(
        self,
        runtime_mode: str = WORLD_V2_MARKET_RUNTIME_MODE,
    ) -> dict[str, object]:
        return runtime_readiness(runtime_mode, getattr(self._runtime_for_mode(runtime_mode), "letta_client", None))

    def ensure_world_runtime_ready(self, runtime_mode: str) -> None:
        ensure_runtime_ready(runtime_mode, getattr(self._runtime_for_mode(runtime_mode), "letta_client", None))

    def queue_world_session(self, session_id: str) -> dict[str, object]:
        rt = self._runtime_for_session(session_id)
        return rt.queue_session(session_id)

    def record_world_session_failure(
        self,
        session_id: str,
        exc: Exception,
        runtime_mode: str | None = None,
    ) -> dict[str, object]:
        if self.world_runtime.store.session_exists(session_id):
            rt = self._runtime_for_session(session_id)
        else:
            mode = runtime_mode or WORLD_V2_MARKET_RUNTIME_MODE
            rt = self._runtime_for_mode(mode)
        return rt.fail_session(session_id, exc)

    def _selected_world_strategies(
        self,
        assets,
        strategy_ids: list[str] | None,
        runtime_mode: str,
    ) -> dict[str, object]:
        selected = select_strategies(assets.strategies, strategy_ids)
        if runtime_mode != WORLD_V2_MARKET_RUNTIME_MODE:
            return selected
        market_catalog = build_market_v2_catalog(chart_count=len(assets.chart_profiles))
        return {
            strategy_id: market_catalog.get(strategy_id, strategy)
            for strategy_id, strategy in selected.items()
        }

    def _ensure_world_v2_kuzu_synced(
        self,
        runtime_mode: str,
        assets: WorkspaceAssets,
    ) -> dict[str, object] | None:
        if runtime_mode != WORLD_V2_MARKET_RUNTIME_MODE:
            return None
        target_draw = assets.pending_draws[-1] if assets.pending_draws else None
        graph_docs = [
            *grounding_documents(assets.knowledge_documents, target_draw),
            *prompt_documents(assets.knowledge_documents),
        ]
        return self.kuzu_graph_service.sync_workspace(
            graph_docs,
            assets.chart_profiles,
            assets.completed_draws,
            assets.pending_draws,
            False,
        )

    def _assets_for_visible_through_period(
        self,
        assets: WorkspaceAssets,
        visible_through_period: str | None,
    ) -> WorkspaceAssets:
        visible_through_period = _optional_string(visible_through_period)
        if not visible_through_period:
            return assets
        for index, draw in enumerate(assets.completed_draws):
            if draw.period != visible_through_period:
                continue
            next_pending = self._next_visible_pending_draw(assets, index + 1)
            if next_pending is None:
                raise ValueError(f"Visible-through period {visible_through_period} has no next issue to predict.")
            return replace(
                assets,
                completed_draws=assets.completed_draws[: index + 1],
                pending_draws=(next_pending,),
            )
        raise ValueError(f"Visible-through period {visible_through_period} not found in workspace draws.")

    def _next_visible_pending_draw(
        self,
        assets: WorkspaceAssets,
        next_index: int,
    ):
        if next_index < len(assets.completed_draws):
            return replace(assets.completed_draws[next_index], numbers=())
        if assets.pending_draws:
            return replace(assets.pending_draws[0], numbers=())
        return None

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
        runtime_mode: str,
        warmup_size: int,
        live_interview_enabled: bool,
        budget_yuan: int,
        session_id: str | None,
        execution_overrides: dict[str, object] | None,
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
            runtime_mode,
            warmup_size,
            budget_yuan,
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
            runtime_mode,
            warmup_size,
            live_interview_enabled,
            budget_yuan,
            session_id,
            self.execution_registry.normalize_overrides(execution_overrides),
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _no_mcp_world_v2_client(execution_registry: ExecutionRegistry):
    if not allow_world_v2_without_mcp():
        return None
    reload_project_env()
    backend = world_v2_no_mcp_backend()
    has_letta = bool(str(os.environ.get("LETTA_BASE_URL", "")).strip())
    if backend == NO_MCP_BACKEND_LETTA:
        if not has_letta:
            raise ValueError("LOTTERY_WORLD_NO_MCP_BACKEND=letta requires LETTA_BASE_URL")
        return LettaNoMcpClient()
    if backend == NO_MCP_BACKEND_LOCAL:
        return LocalWorldClient(execution_registry=execution_registry)
    if has_letta:
        return LettaNoMcpClient()
    return LocalWorldClient(execution_registry=execution_registry)


def _world_v2_no_mcp_client(execution_registry: ExecutionRegistry):
    if len(inspect.signature(_no_mcp_world_v2_client).parameters) == 0:
        return _no_mcp_world_v2_client()
    return _no_mcp_world_v2_client(execution_registry)
