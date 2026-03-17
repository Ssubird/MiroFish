"""Lottery research orchestration service."""

from __future__ import annotations

from ...config import Config
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
from .document_filters import grounding_documents, prompt_documents
from .world_runtime import LotteryWorldRuntime
from .world_v2_runtime import LotteryWorldV2Runtime
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
        self.world_v2_runtime = LotteryWorldV2Runtime(
            runtime.graph_service,
            store=self.world_runtime.store,
            kuzu_graph_service=runtime.kuzu_graph_service,
        )
        self.kuzu_graph_service = runtime.kuzu_graph_service
        self.zep_graph_service = runtime.zep_graph_service
        self.report_writer = report_writer or LotteryReportWriter()

    def _runtime_for_mode(self, runtime_mode: str):
        if runtime_mode == WORLD_V2_MARKET_RUNTIME_MODE:
            return self.world_v2_runtime
        return self.world_runtime

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
        )
        assets = self.runtime.load_workspace()
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
        return self.advance_world_session(**{**kwargs, "runtime_mode": WORLD_V1_RUNTIME_MODE})

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
        runtime_mode: str = WORLD_V1_RUNTIME_MODE,
        warmup_size: int = WORLD_WARMUP_ISSUES,
        live_interview_enabled: bool = DEFAULT_LIVE_INTERVIEW_ENABLED,
        budget_yuan: int = DEFAULT_BUDGET_YUAN,
        session_id: str | None = None,
        assets: WorkspaceAssets | None = None,
        target_period: str | None = None,
    ) -> dict[str, object]:
        del evaluation_size
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
        )
        if assets is None:
            assets = self.runtime.load_workspace()
            if target_period:
                from dataclasses import replace
                target_idx = -1
                for i, d in enumerate(assets.completed_draws):
                    if d.period == target_period:
                        target_idx = i
                        break
                if target_idx != -1:
                    mock_completed = assets.completed_draws[:target_idx]
                    mock_pending = [replace(assets.completed_draws[target_idx], numbers=())]
                    assets = replace(
                        assets,
                        completed_draws=mock_completed,
                        pending_draws=tuple(mock_pending)
                    )
                else:
                    raise ValueError(f"Target period {target_period} not found in historical completed draws.")

        selected = select_strategies(assets.strategies, strategy_ids)
        rt = self._runtime_for_mode(runtime_mode)
        payload = rt.advance(assets, selected, pick_size, options)
        payload["report_artifacts"] = self.report_writer.write(payload)
        rt.store.save_result(payload["world_session"]["session_id"], payload)
        rt.attach_report_artifacts(payload["world_session"]["session_id"], payload["report_artifacts"])
        return payload

    def run_world_evolution(
        self,
        iterations: int = 3,
        **kwargs
    ) -> dict[str, object]:
        from dataclasses import replace
        assets = self.runtime.load_workspace()
        
        if len(assets.completed_draws) < iterations:
            raise ValueError(f"Not enough completed draws for {iterations} iterations.")
            
        kwargs["runtime_mode"] = WORLD_V2_MARKET_RUNTIME_MODE
        
        results = []
        for step in range(iterations, 0, -1):
            mock_completed = assets.completed_draws[:-step]
            mock_pending = list(assets.completed_draws[-step:])
            
            masked_pending = []
            for d in mock_pending:
                masked = replace(d, numbers=())
                masked_pending.append(masked)
                
            mock_assets = replace(
                assets,
                completed_draws=mock_completed,
                pending_draws=tuple(masked_pending)
            )
            
            if results:
                kwargs["session_id"] = results[-1]["world_session"]["session_id"]
                
            payload = self.advance_world_session(assets=mock_assets, **kwargs)
            results.append(payload)
            
        return {
            "evolution_steps": iterations,
            "results": results,
            "final_state": results[-1] if results else None
        }

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
        runtime_mode: str = WORLD_V1_RUNTIME_MODE,
        warmup_size: int = WORLD_WARMUP_ISSUES,
        live_interview_enabled: bool = DEFAULT_LIVE_INTERVIEW_ENABLED,
        budget_yuan: int = DEFAULT_BUDGET_YUAN,
        session_id: str | None = None,
        target_period: str | None = None,
    ) -> dict[str, object]:
        if runtime_mode not in (WORLD_V1_RUNTIME_MODE, WORLD_V2_MARKET_RUNTIME_MODE):
            raise ValueError(f"prepare_world_session unsupported mode: {runtime_mode}")
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
        )
        assets = self.runtime.load_workspace()
        selected = select_strategies(assets.strategies, strategy_ids)
        rt = self._runtime_for_mode(runtime_mode)
        session = rt.prepare_session(assets, selected, pick_size, options.model_name, options.session_id)
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
                "active_agent_ids": session.get("active_agent_ids", []),
                "shared_memory": session["shared_memory"],
                "agents": session["agents"],
                "asset_manifest": session.get("asset_manifest", []),
            },
        }

    def get_world_session(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_session(session_id)

    def get_current_world_session(self) -> dict[str, object]:
        return self.world_runtime.get_current_session()

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
        return self.world_runtime.get_timeline(session_id, offset, limit, latest)

    def interview_world_agent(self, session_id: str, agent_id: str, prompt: str) -> dict[str, object]:
        return self.world_runtime.interview_agent(session_id, agent_id, prompt, self.runtime.load_workspace())

    def get_world_result(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_result(session_id)

    def get_world_graph(self, session_id: str) -> dict[str, object]:
        return self._runtime_for_session(session_id).get_graph(session_id)

    def get_recent_draw_stats(self, session_id: str | None = None) -> dict[str, object]:
        if session_id is None:
            session_id = self.world_runtime.store.current_session_id()
        return self.world_runtime.get_recent_draw_stats(self.runtime.load_workspace(), session_id)

    def finalize_world_result(self, session_id: str) -> dict[str, object]:
        payload = self.get_world_result(session_id)
        if payload.get("report_artifacts"):
            return payload
        payload["report_artifacts"] = self.report_writer.write(payload)
        self.world_runtime.attach_report_artifacts(session_id, payload["report_artifacts"])
        self.world_runtime.store.save_result(session_id, payload)
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
        runtime_mode: str,
        warmup_size: int,
        live_interview_enabled: bool,
        budget_yuan: int,
        session_id: str | None,
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
        )
