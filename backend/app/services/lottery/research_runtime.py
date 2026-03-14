"""Execution runtime for lottery research backtests."""

from __future__ import annotations

from .backtest_support import (
    alternate_numbers,
    attach_latest_prediction,
    build_leaderboard,
    build_process_trace,
    dataset_summary,
    ensemble_breakdown,
    ensemble_contributors,
    ensemble_numbers,
    evaluation_summary,
)
from .catalog import build_strategy_catalog
from .constants import SOCIAL_GROUP, WORLD_WARMUP_ISSUES
from .context import attach_expert_interviews, attach_peer_predictions, build_prediction_context
from .document_filters import grounding_documents
from .graph_runtime import prediction_graph, workspace_graph
from .issue_execution import execute_issue_pipeline
from .performance_summary import build_strategy_performance, performance_rows
from .purchase_plan import PurchasePlanRequest, PurchasePlanService
from .research_types import LLMRunOptions, WindowBacktest, WorkspaceAssets
from .runtime_helpers import by_group, contributor_breakdown, serialized_predictions
from .social_state import SocialStateTracker
from .world_state import WorldStateTracker
from .window_scoring import adaptive_window_required, score_issue_window


OPTIMIZATION_GOAL = "联合优化直接命中、策略 ROI、稳定性惩罚与过热惩罚。"


class LotteryResearchRuntime:
    """Run isolated lottery backtests with injected dependencies."""

    def __init__(
        self,
        repository,
        graph_service,
        dialogue_coordinator,
        zep_graph_service,
        kuzu_graph_service,
        purchase_plan_service=None,
    ):
        self.repository = repository
        self.graph_service = graph_service
        self.dialogue_coordinator = dialogue_coordinator
        self.zep_graph_service = zep_graph_service
        self.kuzu_graph_service = kuzu_graph_service
        self.purchase_plan_service = purchase_plan_service or PurchasePlanService()

    def load_workspace(self) -> WorkspaceAssets:
        draws = self.repository.load_draws()
        completed = tuple(draw for draw in draws if draw.has_numbers)
        pending = tuple(draw for draw in draws if not draw.has_numbers)
        documents = tuple(self.repository.load_knowledge_documents())
        charts = tuple(self.repository.load_chart_profiles())
        target_draw = pending[-1] if pending else None
        grounding_docs = grounding_documents(documents, target_draw)
        zep_digest = self.zep_graph_service.workspace_digest(grounding_docs, charts, completed, pending)
        kuzu_digest = self.kuzu_graph_service.workspace_digest(grounding_docs, charts, completed, pending)
        return WorkspaceAssets(
            completed_draws=completed,
            pending_draws=pending,
            knowledge_documents=documents,
            chart_profiles=charts,
            strategies=build_strategy_catalog(chart_count=len(charts)),
            local_workspace_graph=self.graph_service.build_workspace_graph(
                list(grounding_docs),
                list(charts),
                list(completed),
                target_draw,
            ),
            kuzu_graph_status=self.kuzu_graph_service.status(kuzu_digest),
            zep_graph_status=self.zep_graph_service.status(zep_digest),
        )

    def result_payload(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        evaluation_size: int,
        pick_size: int,
        options: LLMRunOptions,
    ) -> dict[str, object]:
        workspace_snapshot = workspace_graph(
            self.graph_service,
            self.kuzu_graph_service,
            self.zep_graph_service,
            assets,
            options,
        )
        window = self.score_window(assets, strategies, evaluation_size, pick_size, options)
        leaderboard = build_leaderboard(strategies, window.issue_results, pick_size)
        performance = build_strategy_performance(leaderboard)
        pending = self.predict_pending(assets, strategies, leaderboard, performance, window, pick_size, options)
        final_board = attach_latest_prediction(leaderboard, pending["strategy_predictions"]) if pending else leaderboard
        return {
            "dataset": dataset_summary(assets),
            "evaluation": evaluation_summary(
                evaluation_size,
                WORLD_WARMUP_ISSUES,
                pick_size,
                strategies,
                options.request_delay_ms,
                options.model_name,
                options.retry_count,
                options.retry_backoff_ms,
                options.parallelism,
                options.issue_parallelism,
                options.agent_dialogue_enabled,
                options.agent_dialogue_rounds,
                options.graph_mode,
                options.zep_graph_id,
            ),
            "process_trace": build_process_trace(
                assets,
                workspace_snapshot,
                tuple(replay.target_draw for replay in window.issue_replays),
                tuple(replay.target_draw for replay in window.warmup_replays),
                strategies,
                final_board,
                options.agent_dialogue_enabled,
                options.agent_dialogue_rounds,
            ),
            "leaderboard": final_board,
            "pending_prediction": pending,
        }

    def score_window(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        evaluation_size: int,
        pick_size: int,
        options: LLMRunOptions,
    ) -> WindowBacktest:
        social_state = SocialStateTracker(by_group(strategies, SOCIAL_GROUP))
        world_state = WorldStateTracker()
        window = score_issue_window(
            assets.completed_draws,
            evaluation_size,
            strategies,
            lambda task, performance: self._predict_window_issue(
                task,
                assets,
                strategies,
                pick_size,
                options,
                performance,
                social_state,
                world_state,
            ),
            options.issue_parallelism,
            adaptive_window_required(strategies, options.agent_dialogue_enabled),
            WORLD_WARMUP_ISSUES,
        )
        return WindowBacktest(
            window.issue_results,
            window.issue_replays,
            window.warmup_replays,
            window.warmup_size,
            social_state.snapshot(),
            world_state.snapshot(),
        )

    def execute_issue(
        self,
        context,
        strategies: dict[str, object],
        pick_size: int,
        options: LLMRunOptions,
        include_trace: bool = False,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        return execute_issue_pipeline(
            context,
            strategies,
            pick_size,
            options,
            self.dialogue_coordinator,
            include_trace,
        )

    def prediction_context(
        self,
        history_draws,
        target_draw,
        assets: WorkspaceAssets,
        options: LLMRunOptions,
        strategy_performance: dict[str, dict[str, object]] | None = None,
        social_state: dict[str, dict[str, object]] | None = None,
        world_state: dict[str, object] | None = None,
    ):
        return build_prediction_context(
            history_draws=history_draws,
            target_draw=target_draw,
            knowledge_documents=list(grounding_documents(assets.knowledge_documents, target_draw)),
            chart_profiles=list(assets.chart_profiles),
            graph_snapshot=prediction_graph(
                self.graph_service,
                self.kuzu_graph_service,
                self.zep_graph_service,
                history_draws,
                target_draw,
                assets,
                options,
            ),
            llm_request_delay_ms=options.request_delay_ms,
            llm_model_name=options.model_name,
            llm_retry_count=options.retry_count,
            llm_retry_backoff_ms=options.retry_backoff_ms,
            strategy_performance=strategy_performance,
            optimization_goal=OPTIMIZATION_GOAL,
            social_state=social_state,
            world_state=world_state,
        )

    def predict_pending(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        leaderboard: list[dict[str, object]],
        performance: dict[str, dict[str, object]],
        window: WindowBacktest,
        pick_size: int,
        options: LLMRunOptions,
    ) -> dict[str, object] | None:
        if not assets.pending_draws:
            return None
        pending_draw = assets.pending_draws[-1]
        social_state = SocialStateTracker(by_group(strategies, SOCIAL_GROUP), window.social_state)
        world_state = WorldStateTracker(dict(window.world_state))
        context = self.prediction_context(
            list(assets.completed_draws),
            pending_draw,
            assets,
            options,
            performance,
            social_state.snapshot(),
            world_state.snapshot(),
        )
        predictions, trace = self.execute_issue(context, strategies, pick_size, options, True)
        social_state.record_issue(pending_draw.period, predictions, trace)
        interviewed = _interviewed_context(context, predictions)
        world_state.record_issue(pending_draw.period, predictions, trace, interviewed.expert_interviews)
        contributors = ensemble_contributors(leaderboard)
        serialized = serialized_predictions(predictions, leaderboard)
        breakdown = contributor_breakdown(predictions, contributors)
        numbers = ensemble_numbers(breakdown, pick_size)
        alternates = alternate_numbers(breakdown, pick_size)
        purchase_plan = self.purchase_plan_service.build(
            PurchasePlanRequest(
                context=interviewed,
                pending_predictions=predictions,
                strategies=strategies,
                performance=performance,
                window_backtest=window,
                pick_size=pick_size,
                ensemble_numbers=tuple(numbers),
                coordination_trace=tuple(trace),
                alternate_numbers=tuple(alternates),
            )
        )
        return {
            "period": pending_draw.period,
            "date": pending_draw.date,
            "performance_context": performance_rows(performance),
            "strategy_predictions": serialized,
            "coordination_trace": trace,
            "ensemble_numbers": numbers,
            "alternate_numbers": alternates,
            "ensemble_breakdown": ensemble_breakdown(numbers, breakdown),
            "contributors": contributors,
            "social_state": social_state.snapshot(),
            "world_state": world_state.snapshot(),
            "purchase_plan": purchase_plan,
        }

    def _predict_window_issue(
        self,
        task,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        pick_size: int,
        options: LLMRunOptions,
        performance: dict[str, dict[str, object]] | None,
        social_state: SocialStateTracker,
        world_state: WorldStateTracker,
    ) -> dict[str, object]:
        context = self.prediction_context(
            list(task.history),
            task.target_draw,
            assets,
            options,
            performance,
            social_state.snapshot(),
            world_state.snapshot(),
        )
        predictions, trace = self.execute_issue(context, strategies, pick_size, options, True)
        social_state.record_issue(task.target_draw.period, predictions, trace, task.target_draw.numbers)
        interviewed = _interviewed_context(context, predictions)
        world_state.record_issue(
            task.target_draw.period,
            predictions,
            trace,
            interviewed.expert_interviews,
            task.target_draw.numbers,
        )
        return predictions


def _interviewed_context(context, predictions):
    return attach_expert_interviews(attach_peer_predictions(context, predictions), predictions)
