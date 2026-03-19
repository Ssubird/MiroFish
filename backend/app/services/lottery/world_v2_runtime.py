"""Persistent Letta-backed world runtime for lottery prediction."""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Lock
from typing import Any, Iterable

from .backtest_support import (
    alternate_numbers,
    build_leaderboard,
    dataset_summary,
    ensemble_breakdown,
    ensemble_contributors,
    ensemble_numbers,
    evaluation_summary,
)
from .constants import PRIMARY_GROUPS, WORLD_V2_MARKET_RUNTIME_MODE, WORLD_V2_PHASES
from .context import build_prediction_context
from .document_filters import grounding_documents, manual_reference_documents, prompt_documents
from .execution import run_strategy_stage
from .happy8_rules import DEFAULT_BUDGET_YUAN, TICKET_COST_YUAN, ticket_payout
from .letta_client import LettaClient
from .market_diversity import (
    build_social_prompt_view,
)
from .market_role_registry import (
    HANDBOOK_PROMPT_DOC,
    agent_prompt_passages as registry_prompt_passages,
    direct_prompt_block as registry_direct_prompt_block,
    handbook_role_metadata,
)
from .performance_summary import build_strategy_performance, performance_rows
from .purchase_structures import planner_structure
from .research_types import WorkspaceAssets
from .runtime_helpers import contributor_breakdown, serialized_predictions
from .serializers import serialize_prediction
from .world_assets import build_world_asset_manifest
from .world_v2_market import (
    aggregate_number_scores,
    bet_plan_from_payload,
    compatibility_projection,
    deserialize_signal_output,
    market_synthesis_payload,
    reference_leg_payload,
    serialize_bet_plan,
    serialize_signal_output,
    signal_output_from_prediction,
)
from .world_graph import build_world_graph
from .world_models import WorldAgentRef, WorldEvent, WorldSession, world_id, world_now
from .world_execution_log import append_execution_log, build_error_payload
from .world_store import WorldSessionStore
from .world_support import (
    agent_blocks,
    comment_schema,
    debate_schema,
    ensure_alternate_numbers,
    initial_shared_memory,
    issue_block,
    merge_issue_discussion,
    NO_HANDBOOK_PRINCIPLES,
    NO_MARKET_BOARD,
    NO_PURCHASE_BOARD,
    NO_SOCIAL_FEED,
    parse_json_response,
    prediction_prompt,
    prompt_passages,
    purchase_rule_block,
    purchase_schema,
    recent_outcomes_text,
    report_digest,
    rule_digest,
)
from .world_stats import build_recent_draw_stats
from .catalog import build_market_v2_catalog
from ...config import reload_project_env


ROUND_PHASES = WORLD_V2_PHASES
SHARED_BLOCKS = (
    "world_goal",
    "current_issue",
    "visible_draw_history_digest",
    "market_board",
    "social_feed",
    "purchase_board",
    "handbook_principles",
    "final_decision_constraints",
    "recent_outcomes",
    "report_digest",
    "rule_digest",
    "purchase_budget",
)
AGENT_BLOCK_SCHEMA_VERSION = 5
PURCHASE_PLAN_REPAIR_ATTEMPTS = 2
PURCHASE_PLAN_RAW_PREVIEW_CHARS = 1200
MCP_SERVER_NAMES = (
    "happy8_rules_mcp",
    "world_state_mcp",
    "kuzu_market_mcp",
    "report_memory_mcp",
)
WORLD_ROLES = (
    (
        "purchase_chair",
        "LLM-Purchase-Chair",
        "purchase",
        "purchase",
        "Synthesize the final executable market plan after reading bettor flow, judge boards, reports, and rule constraints.",
    ),
    (
        "handbook_decider",
        "Handbook Decider",
        "decision",
        "decision",
        "Read all generator boards, market discussion, purchase recommendation, and recent reviews, then publish the official final prediction for the next issue.",
    ),
)


class LotteryWorldV2Runtime:
    """Run the persistent `world_v2_market` lottery session."""

    def __init__(
        self,
        graph_service,
        store: WorldSessionStore | None = None,
        letta_client: LettaClient | None = None,
        kuzu_graph_service=None,
    ):
        self.graph_service = graph_service
        self.store = store or WorldSessionStore()
        self.letta_client = letta_client
        self.kuzu_graph_service = kuzu_graph_service
        self._client_cache: dict[str, LettaClient] = {}
        self._metric_lock = Lock()

    def run_backtest(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        evaluation_size: int,
        pick_size: int,
        options,
    ) -> dict[str, Any]:
        del evaluation_size
        return self.advance(assets, strategies, pick_size, options)

    def advance(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        pick_size: int,
        options,
    ) -> dict[str, Any]:
        self._validate_request(pick_size, options.issue_parallelism)
        target_draw = _pending_target_draw(assets)
        session = self.prepare_session(assets, strategies, pick_size, options.model_name, options.session_id)
        self._apply_runtime_budget(session, options.budget_yuan)
        session["visible_through_period"] = _visible_through_period(assets)
        self._sync_asset_manifest(session, target_draw.period)
        try:
            self._maybe_settle(session, assets, strategies, pick_size, options)
            if self._is_waiting_for_same_target(session, target_draw.period):
                payload = self._payload(session, assets, strategies, pick_size, options)
                self.store.save_result(session["session_id"], payload)
                return payload
            self._run_prediction_cycle(session, assets, strategies, target_draw, pick_size, options)
            payload = self._payload(session, assets, strategies, pick_size, options)
            self.store.save_result(session["session_id"], payload)
            return payload
        except Exception as exc:
            payload = self._mark_failed(session, assets, strategies, pick_size, options, exc)
            self.store.save_result(session["session_id"], payload)
            raise

    def prepare_session(
        self,
        assets: WorkspaceAssets,
        strategies: dict[str, object],
        pick_size: int,
        model_name: str | None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if session_id and self.store.session_exists(session_id):
            session = self.store.load_session(session_id)
            if _session_compatible(session, strategies):
                return session
        if not session_id:
            current_id = self.store.current_session_id()
            if current_id and self.store.session_exists(current_id):
                session = self.store.load_session(current_id)
                if _session_compatible(session, strategies):
                    return session
        target_draw = _pending_target_draw(assets)
        session = self._create_session(strategies, pick_size, model_name, DEFAULT_BUDGET_YUAN, session_id)
        self._sync_asset_manifest(session, target_draw.period)
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "session_started", "Persistent world session created.")])
        return session

    def get_current_session(self) -> dict[str, Any]:
        session = self.store.load_current_session()
        return self.get_session(str(session["session_id"]))

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        return {
            "session": session,
            "timeline_preview": self.store.list_events(session_id, 0, 20, latest=True)["items"],
            "purchase_committee_state": session.get("latest_purchase_plan", {}),
            "result_available": self.store.result_exists(session_id),
            "report_artifacts": session.get("report_artifacts"),
        }

    def get_timeline(self, session_id: str, offset: int, limit: int, latest: bool = False) -> dict[str, Any]:
        return self.store.list_events(session_id, offset, limit, latest)

    def get_result(self, session_id: str) -> dict[str, Any]:
        return self.store.load_result(session_id)

    def get_graph(self, session_id: str) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        timeline = self.store.list_events(session_id, 0, 400, latest=True)
        return build_world_graph(session, timeline["items"])

    def get_recent_draw_stats(
        self,
        assets: WorkspaceAssets,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        timeline_rows = []
        if session_id and self.store.session_exists(session_id):
            timeline_rows = self.store.list_events(session_id, 0, 240, latest=True)["items"]
        return build_recent_draw_stats(assets.completed_draws, timeline_rows)

    def queue_session(self, session_id: str) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        if session.get("status") == "queued":
            return session
        session["status"] = "queued"
        session["current_phase"] = "queued"
        session["failed_phase"] = None
        session["error"] = None
        self._log_execution(
            session,
            "info",
            "session_queued",
            "后台 world 任务已入队，等待执行。",
            phase="queued",
        )
        self._persist_session(session)
        return session

    def fail_session(self, session_id: str, exc: Exception) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        error = build_error_payload(
            exc,
            phase=str(session.get("current_phase") or "idle"),
            period=session.get("current_period"),
        )
        message = error["message"]
        current_error = session.get("error") or {}
        if session.get("status") == "failed" and current_error.get("message") == message:
            return session
        failed_phase = session.get("current_phase") or "idle"
        session["status"] = "failed"
        session["failed_phase"] = failed_phase
        session["current_phase"] = "failed"
        session["error"] = error
        self._log_execution(
            session,
            "error",
            error.get("code", "world_runtime_failed"),
            message,
            phase=failed_phase,
            details=error.get("details"),
        )
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "run_failed", message)])
        return session

    def attach_report_artifacts(self, session_id: str, artifacts: dict[str, object]) -> None:
        session = self.store.load_session(session_id)
        session["report_artifacts"] = artifacts
        self._persist_session(session)

    def interview_agent(
        self,
        session_id: str,
        agent_id: str,
        prompt: str,
        assets: WorkspaceAssets | None = None,
    ) -> dict[str, Any]:
        session = self.store.load_session(session_id)
        display_name = agent_id
        group = "-"
        if _session_has_agent(session, agent_id):
            agent = _agent_by_id(session, agent_id)
            answer = self._send_message(session, agent["letta_agent_id"], _interview_prompt(session, prompt))
            display_name = agent["display_name"]
            group = agent.get("group", "-")
        else:
            answer, display_name, group = _deterministic_interview_answer(session, agent_id, prompt)
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            session.get("current_phase") or "idle",
            "external_interview",
            agent_id,
            display_name,
            answer,
            metadata={"group": group, "question": prompt},
        )
        self._append_events(session, [event])
        self._append_public_discussion(session, [event], persist=True)
        return {"agent_id": agent_id, "display_name": display_name, "answer": answer}

    def _validate_request(self, pick_size: int, issue_parallelism: int) -> None:
        if issue_parallelism != 1:
            raise ValueError("world_v2_market requires issue_parallelism=1")

    def _maybe_settle(self, session, assets, strategies, pick_size: int, options) -> None:
        latest = dict(session.get("latest_prediction", {}))
        if not latest:
            return
        period = str(latest.get("period", "")).strip()
        if not period or _period_already_settled(session, period):
            return
        actual_draw = _completed_draw_lookup(assets).get(period)
        if actual_draw is None:
            session["status"] = "await_result"
            session["current_phase"] = "await_result"
            session["current_period"] = period
            session.setdefault("progress", {})["completion_message"] = "预测完成，等待开奖"
            self._persist_session(session)
            return
        self._run_settlement_cycle(session, strategies, actual_draw, pick_size, options)

    
    def _run_prediction_cycle(self, session, assets, strategies, target_draw, pick_size: int, options) -> None:
        session["status"] = "running"
        session["current_period"] = target_draw.period
        session["_all_documents"] = assets.knowledge_documents
        self._log_execution(
            session,
            "info",
            "prediction_cycle_start",
            f"开始执行 world_v2_market，目标期次 {target_draw.period}。",
            details=[
                f"strategy_count={len(strategies)}",
                f"llm_model={session.get('llm_model_name') or options.model_name or '-'}",
                f"budget_yuan={session.get('budget_yuan', DEFAULT_BUDGET_YUAN)}",
                f"llm_parallelism={options.parallelism}",
            ],
        )
        self._persist_session(session)
        leaderboard, performance = self._performance(strategies, session, pick_size)
        context = self._context(list(assets.completed_draws), target_draw, assets, options, performance, session)
        self._ensure_market_tooling(session)
        self._ensure_agents(session, strategies, context)
        round_state = self._load_round_state(session, target_draw)
        self._refresh_round_cache_context(session, round_state, assets, target_draw.period, options)
        self._save_round_state(session, round_state)
        
        # 1. generator_opening
        signals, signal_outputs = self._phase_generator_opening(
            session,
            round_state,
            context,
            strategies,
            pick_size,
            options.parallelism,
            leaderboard,
        )
        
        # 2. social_propagation
        social_posts, interviews = self._phase_social_propagation(
            session,
            round_state,
            context,
            signals,
            signal_outputs,
            performance,
            pick_size,
            options,
            leaderboard,
        )
        
        # 3. market_rerank
        market_ranks = self._phase_market_rerank(
            session,
            round_state,
            context,
            signal_outputs,
            social_posts,
            leaderboard,
            options.parallelism,
        )
        
        # 4. plan_synthesis
        synthesis, final_plan = self._phase_plan_synthesis(
            session,
            round_state,
            target_draw.period,
            signal_outputs,
            social_posts,
            market_ranks,
        )

        # 5. handbook_final_decision
        final_decision = self._phase_handbook_final_decision(
            session,
            round_state,
            target_draw,
            signal_outputs,
            social_posts,
            market_ranks,
            final_plan,
            leaderboard,
        )
        
        self._finalize_await_result(
            session,
            round_state,
            target_draw,
            signals,
            signal_outputs,
            synthesis,
            final_plan,
            final_decision,
            interviews,
            social_posts,
            market_ranks,
            leaderboard,
        )

    def _phase_generator_opening(self, session, round_state, context, strategies, pick_size: int, parallelism: int, leaderboard):
        cached = _deserialize_prediction_map(round_state.get("signal_predictions", {}))
        cached_outputs = [
            deserialize_signal_output(item)
            for item in round_state.get("signal_outputs", [])
            if isinstance(item, dict)
        ]
        if cached and cached_outputs and self._can_skip_phase(session, "generator_opening"):
            return cached, cached_outputs
        self._set_phase(session, "generator_opening")
        predictions = self._opening_predictions(context, strategies, pick_size, parallelism)
        performance = _leaderboard_performance(leaderboard)
        signal_outputs = [
            signal_output_from_prediction(prediction, performance.get(strategy_id))
            for strategy_id, prediction in predictions.items()
        ]
        self._update_shared_memory(session, context, predictions, performance)
        events = self._opening_events(session, context.target_draw.period, predictions)
        self._append_events(session, events)
        round_state["signal_predictions"] = _serialize_prediction_map(predictions, leaderboard)
        round_state["signal_outputs"] = [serialize_signal_output(item) for item in signal_outputs]
        round_state["opening_events"] = [item.to_dict() for item in events]
        self._set_issue_summary(
            session,
            period=context.target_draw.period,
            phase="generator_opening",
            primary_numbers=[],
            alternate_numbers=[],
            top_strategy_numbers={key: list(item.numbers) for key, item in list(predictions.items())[:6]},
        )
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._complete_phase(session, "generator_opening")
        return predictions, signal_outputs

    def _phase_social_propagation(self, session, round_state, context, signals, signal_outputs, performance, pick_size: int, options, leaderboard):
        cached_posts = list(round_state.get("social_events", []))
        if cached_posts and self._can_skip_phase(session, "social_propagation"):
            self._refresh_social_feed_block(session, cached_posts)
            return cached_posts, list(round_state.get("interviews", []))
        self._set_phase(session, "social_propagation")
        
        interviews = []
        if options.live_interview_enabled:
            interview_events = self._interviews(session, context, signals, performance, options.parallelism)
            interviews = [item.to_dict() for item in interview_events]
            self._append_events(session, interview_events)
            self._append_public_discussion(session, interview_events)

        social_events = self._social_posts(
            session,
            context,
            signal_outputs,
            performance,
            options.agent_dialogue_enabled,
            options.agent_dialogue_rounds,
        )
        self._append_events(session, social_events)
        self._append_public_discussion(session, social_events, persist=True)
        self._refresh_social_feed_block(session, [item.to_dict() for item in social_events])
        round_state["interviews"] = interviews
        round_state["social_events"] = [item.to_dict() for item in social_events]
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._complete_phase(session, "social_propagation")
        return social_events, interviews

    def _phase_market_rerank(self, session, round_state, context, signal_outputs, social_posts, leaderboard, parallelism: int):
        cached = list(round_state.get("market_ranks", []))
        if cached and self._can_skip_phase(session, "market_rerank"):
            self._refresh_market_board_block(session, signal_outputs, social_posts, cached, leaderboard)
            return cached
        self._set_phase(session, "market_rerank")
        judge_boards = self._judge_boards(session, signal_outputs, social_posts, leaderboard, parallelism)
        self._append_events(session, judge_boards)
        ranks = [item.to_dict() for item in judge_boards]
        self._refresh_market_board_block(session, signal_outputs, social_posts, ranks, leaderboard)
        round_state["market_ranks"] = ranks
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._complete_phase(session, "market_rerank")
        return ranks

    def _phase_plan_synthesis(self, session, round_state, period: str, signal_outputs, social_posts, market_ranks):
        if "plan_synthesis" in round_state and self._can_skip_phase(session, "plan_synthesis"):
            self._refresh_purchase_board_block(session, dict(round_state.get("final_plan", {})))
            return round_state["plan_synthesis"], dict(round_state.get("final_plan", {}))
        self._set_phase(session, "plan_synthesis")

        synthesis, final_plan, event = self._synthesize_market(
            session,
            signal_outputs,
            social_posts,
            market_ranks,
        )
        round_state["plan_synthesis"] = synthesis
        round_state["final_plan"] = final_plan
        round_state["compatibility_projection"] = compatibility_projection(synthesis, final_plan)
        if event is not None:
            self._append_events(session, [event])
        compat = round_state["compatibility_projection"]
        self._set_issue_summary(
            session,
            period=period,
            phase="plan_synthesis",
            primary_numbers=list(compat.get("ensemble_numbers", [])),
            alternate_numbers=list(compat.get("alternate_numbers", [])),
            trusted_strategy_ids=list(synthesis.get("trusted_strategy_ids", [])),
            purchase_plan_type=final_plan.get("plan_type"),
            purchase_play_size=final_plan.get("play_size"),
            purchase_ticket_count=final_plan.get("ticket_count"),
        )
        session["latest_purchase_plan"] = final_plan
        self._refresh_purchase_board_block(session, final_plan)
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._complete_phase(session, "plan_synthesis")
        return synthesis, final_plan

    def _phase_handbook_final_decision(
        self,
        session,
        round_state,
        target_draw,
        signal_outputs,
        social_posts,
        market_ranks,
        final_plan,
        leaderboard,
    ):
        if "final_decision" in round_state and self._can_skip_phase(session, "handbook_final_decision"):
            return dict(round_state["final_decision"])
        self._set_phase(session, "handbook_final_decision")
        final_decision, event = self._handbook_final_decision(
            session,
            target_draw.period,
            signal_outputs,
            social_posts,
            market_ranks,
            final_plan,
            leaderboard,
        )
        round_state["final_decision"] = final_decision
        if event is not None:
            self._append_events(session, [event])
        self._set_issue_summary(
            session,
            period=target_draw.period,
            phase="handbook_final_decision",
            primary_numbers=list(final_decision.get("numbers", [])),
            alternate_numbers=list(final_decision.get("alternate_numbers", [])),
            trusted_strategy_ids=list(final_decision.get("trusted_strategy_ids", [])),
        )
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._complete_phase(session, "handbook_final_decision")
        return final_decision


    
    def _finalize_await_result(
        self,
        session,
        round_state,
        target_draw,
        signals,
        signal_outputs,
        synthesis,
        final_plan,
        final_decision,
        interviews,
        social_posts,
        market_ranks,
        leaderboard,
    ) -> None:
        coordination = _round_trace(round_state, [])
        session["status"] = "await_result"
        session["current_phase"] = "await_result"
        session["failed_phase"] = None
        session["current_period"] = target_draw.period
        session["progress"]["awaiting_period"] = target_draw.period
        session["progress"]["completion_message"] = "预测完成，等待开奖"
        round_state["status"] = "await_result"
        round_state["updated_at"] = world_now()
        compatibility = dict(round_state.get("compatibility_projection", {}))
        market_discussion = {
            "social_posts": [item if isinstance(item, dict) else item.to_dict() for item in social_posts],
            "judge_boards": [item if isinstance(item, dict) else item.to_dict() for item in market_ranks],
            "live_interviews": interviews,
        }
        session["latest_prediction"] = {
            "period": target_draw.period,
            "date": target_draw.date,
            "visible_through_period": session.get("visible_through_period"),
            "predicted_period": target_draw.period,
            "generator_boards": [serialize_signal_output(item) for item in signal_outputs],
            "market_discussion": market_discussion,
            "purchase_recommendation": dict(final_plan),
            "final_decision": dict(final_decision),
            "ensemble_numbers": list(final_decision.get("numbers", [])),
            "alternate_numbers": list(final_decision.get("alternate_numbers", [])),
            "strategy_predictions": serialized_predictions(signals, leaderboard),
            "performance_context": performance_rows(_leaderboard_performance(leaderboard)),
            "coordination_trace": coordination,
            "social_state": session.get("agent_state", {}),
            "world_state": {
                "settlement_history": session.get("settlement_history", []),
                "round_history": session.get("round_history", []),
                "issue_ledger": session.get("issue_ledger", []),
            },
            "latest_review": session.get("latest_review", {}),
        }
        session["latest_purchase_plan"] = dict(final_plan)
        
        # update summary again to be sure
        self._set_issue_summary(
            session,
            period=target_draw.period,
            phase="await_result",
            primary_numbers=list(final_decision.get("numbers", [])),
            alternate_numbers=list(final_decision.get("alternate_numbers", [])),
            trusted_strategy_ids=list(final_decision.get("trusted_strategy_ids", [])),
        )
        self._save_round_state(session, round_state)
        self._mark_runtime_projection_dirty(session)
        self._flush_runtime_projection(session)
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "await_result", f"Waiting for draw result: {target_draw.period}")])

    def _run_settlement_cycle(self, session, strategies, actual_draw, pick_size: int, options) -> None:
        del strategies, pick_size
        round_state = dict(session.get("current_round", {}))
        if not round_state:
            return
        signals = _deserialize_prediction_map(
            round_state.get("signal_predictions", {})
        )
        market_synthesis = dict(round_state.get("plan_synthesis", {}))
        final_plan = dict(round_state.get("final_plan", {}))
        final_decision = dict(round_state.get("final_decision", {}))
        
        if not signals or not market_synthesis or not final_plan or not final_decision:
            return
            
        self._set_phase(session, "settlement")
        settlement = self._settle(session, actual_draw, signals, market_synthesis, final_plan, final_decision)
        self._complete_phase(session, "settlement")
        
        self._set_phase(session, "postmortem")
        events = self._postmortem(
            session,
            actual_draw,
            signals,
            market_synthesis,
            final_plan,
            final_decision,
            options.parallelism,
        )
        self._append_events(session, events)
        latest_review = _latest_review_payload(
            actual_draw,
            final_decision,
            final_plan,
            settlement,
            events,
        )
        
        round_state["status"] = "settled"
        round_state["actual_numbers"] = list(actual_draw.numbers)
        round_state["postmortem_events"] = [item.to_dict() for item in events]
        round_state["latest_review"] = latest_review
        round_state["updated_at"] = world_now()
        
        session["round_history"].append(round_state)
        session["latest_review"] = latest_review
        session["issue_ledger"].append(
            _issue_ledger_entry(
                session,
                actual_draw,
                final_decision,
                final_plan,
                settlement,
                latest_review,
                round_state,
            )
        )
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["status"] = "idle"
        session["current_phase"] = "idle"
        session["current_period"] = None
        session["progress"]["awaiting_period"] = None
        session["progress"]["settled_rounds"] = int(session.get("progress", {}).get("settled_rounds", 0)) + 1
        session["progress"]["completion_message"] = "复盘完成"
        session["progress"]["last_review_period"] = actual_draw.period
        session["failed_phase"] = None
        session["last_success_phase"] = "postmortem"
        self._set_issue_summary(
            session,
            period=actual_draw.period,
            phase="postmortem",
            primary_numbers=[],
            alternate_numbers=[],
            actual_numbers=list(actual_draw.numbers),
        )
        self._mark_runtime_projection_dirty(session)
        self._flush_runtime_projection(session)
        self._persist_session(session)

    def _settle(self, session, actual_draw, signals, market_synthesis, final_plan, final_decision) -> dict[str, Any]:
        actual = set(actual_draw.numbers)
        reference_leg = reference_leg_payload(final_plan)
        reference_numbers = list(reference_leg.get("numbers", []))
        official_numbers = [int(value) for value in final_decision.get("numbers", [])]
        official_alternates = [int(value) for value in final_decision.get("alternate_numbers", [])]
        hedge_pool = [int(value) for value in market_synthesis.get("hedge_pool", [])]
        strategy_issue_results = {}
        hits = {}
        for strategy_id, prediction in signals.items():
            hit_count = len(actual & set(prediction.numbers))
            hits[strategy_id] = hit_count
            strategy_issue_results[strategy_id] = {
                "period": actual_draw.period,
                "date": actual_draw.date,
                "hits": hit_count,
                "predicted_numbers": list(prediction.numbers),
                "actual_numbers": list(actual_draw.numbers),
                "group": prediction.group,
            }
            state = _agent_state_row(session, strategy_id, prediction.display_name, prediction.rationale)
            state["recent_hits"].append(hit_count)
        best_hits = max(hits.values(), default=0)
        reference_tickets = _plan_tickets(final_plan)
        reference_cost = int(final_plan.get("total_cost_yuan", 0) or 0)
        reference_payout = _purchase_payout(reference_tickets, actual_draw.numbers) or 0
        purchase_profit = reference_payout - reference_cost
        purchase_roi = round(purchase_profit / reference_cost, 4) if reference_cost else 0.0
        settlement = {
            "period": actual_draw.period,
            "official_prediction": official_numbers,
            "official_alternate_numbers": official_alternates,
            "consensus_numbers": official_numbers,
            "alternate_numbers": official_alternates or hedge_pool,
            "actual_numbers": list(actual_draw.numbers),
            "official_hits": len(actual & set(official_numbers)),
            "consensus_hits": len(actual & set(official_numbers)),
            "reference_plan_id": market_synthesis.get("reference_plan_id"),
            "reference_plan_type": final_plan.get("plan_type"),
            "reference_leg_numbers": reference_numbers,
            "reference_leg_hits": len(actual & set(reference_numbers)),
            "best_hits": best_hits,
            "best_strategy_ids": [sid for sid, value in hits.items() if value == best_hits][:3],
            "purchase_profit": purchase_profit,
            "purchase_cost_yuan": reference_cost,
            "purchase_payout_yuan": reference_payout,
            "purchase_roi": purchase_roi,
            "reference_plan_profit": purchase_profit,
            "reference_plan_payout": reference_payout,
            "total_market_volume_yuan": reference_cost,
            "market_profit": purchase_profit,
            "strategy_issue_results": strategy_issue_results,
        }
        session["settlement_history"].append(settlement)
        session["shared_memory"]["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        self._sync_shared_blocks(session)
        self._persist_session(session)
        return settlement


    def _postmortem(
        self,
        session,
        actual_draw,
        predictions,
        market_synthesis,
        final_plan,
        final_decision,
        parallelism: int,
    ) -> list[WorldEvent]:
        reference_leg = reference_leg_payload(final_plan)
        summary = (
            f"Actual numbers: {list(actual_draw.numbers)}\n"
            f"Reference ticket: {reference_leg['numbers']}\n"
            f"Hedge pool: {list(market_synthesis.get('hedge_pool', []))}\n"
            f"Reference plan type: {final_plan.get('plan_type', '-')}\n"
            f"Official final prediction: {list(final_decision.get('numbers', []))}\n"
            "Summarize what was right, what was wrong, and what to adjust in the market next."
            f"\n{comment_schema()}"
        )
        agent_ids = [agent_id for agent_id in session.get("active_agent_ids", []) if _session_has_agent(session, agent_id)]
        events = _parallel_results(
            agent_ids,
            parallelism,
            lambda agent_id: self._commentary(session, agent_id, "postmortem", summary),
        )
        session["shared_memory"]["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        self._append_public_discussion(session, events, persist=True)
        return events

    def _opening_predictions(self, context, strategies, pick_size: int, parallelism: int):
        grouped = _grouped_generator_strategies(strategies)
        predictions = {}
        for group_name in PRIMARY_GROUPS:
            stage_strategies = grouped.get(group_name, {})
            if not stage_strategies:
                continue
            predictions.update(run_strategy_stage(context, stage_strategies, pick_size, parallelism))
        return predictions

    def _context(self, history, target_draw, assets, options, performance, session):
        visible_docs = tuple(grounding_documents(assets.knowledge_documents, target_draw))
        graph = self._prediction_graph(history, target_draw, assets)
        return build_prediction_context(
            history,
            target_draw,
            list(visible_docs),
            list(assets.chart_profiles),
            graph_snapshot=graph,
            llm_request_delay_ms=options.request_delay_ms,
            llm_model_name=options.model_name,
            llm_retry_count=options.retry_count,
            llm_retry_backoff_ms=options.retry_backoff_ms,
            strategy_performance=performance,
            social_state=session.get("agent_state", {}),
            world_state={
                "settlement_history": session.get("settlement_history", []),
                "round_history": session.get("round_history", []),
                "issue_ledger": session.get("issue_ledger", []),
                "latest_review": session.get("latest_review", {}),
            },
            prompt_documents=list(prompt_documents(assets.knowledge_documents)),
        )

    def _prediction_graph(self, history, target_draw, assets):
        if self.kuzu_graph_service is None:
            return self.graph_service.build_prediction_graph(
                history,
                target_draw,
                list(grounding_documents(assets.knowledge_documents, target_draw)),
                list(assets.chart_profiles),
            )
        graph_docs = [
            *grounding_documents(assets.knowledge_documents, target_draw),
            *prompt_documents(assets.knowledge_documents),
        ]
        return self.kuzu_graph_service.build_prediction_graph(
            history,
            target_draw,
            graph_docs,
            assets.chart_profiles,
        )

    def _ensure_market_tooling(self, session) -> None:
        if self._mcp_disabled_mode():
            backend = self._runtime_backend()
            session["mcp_tools"] = {}
            self._log_execution(
                session,
                "info",
                f"{backend}_mode",
                "已启用显式无 MCP 运行模式，跳过 Letta/MCP 工具注册。",
                details=[f"runtime_backend={backend}"],
            )
            self._persist_session(session)
            return
        if session.get("mcp_tools"):
            self._log_execution(
                session,
                "info",
                "mcp_tooling_reused",
                "复用已注册的 MCP 工具映射。",
            )
            return
        self._log_execution(
            session,
            "info",
            "mcp_tooling_start",
            "开始注册并同步 market runtime 所需的 MCP 工具。",
            details=[f"servers={', '.join(MCP_SERVER_NAMES)}"],
        )
        client = self._client(session)
        existing = {
            str(item.get("server_name", "")).strip(): item
            for item in client.list_mcp_servers()
            if str(item.get("server_name", "")).strip()
        }
        server_tools = {}
        for server_name in MCP_SERVER_NAMES:
            config = self._mcp_server_config(server_name, session)
            self._log_execution(
                session,
                "info",
                "mcp_server_prepare",
                f"准备 MCP server: {server_name}",
                details=[f"type={config.get('type', '-')}", f"command={config.get('command', '-')}"],
            )
            try:
                if server_name not in existing:
                    client.add_mcp_server(config)
                client.connect_mcp_server(config)
                client.resync_mcp_server_tools(server_name)
                tools = {}
                for item in client.list_mcp_tools_by_server(server_name):
                    tool_name = str(item.get("name") or item.get("tool_name") or "").strip()
                    tool_id = str(item.get("id") or "").strip()
                    if tool_name and tool_id:
                        tools[tool_name] = tool_id
                if not tools:
                    raise ValueError(f"MCP server {server_name} registered but exposed no tools")
            except Exception as exc:
                self._log_execution(
                    session,
                    "error",
                    "mcp_server_prepare_failed",
                    f"MCP server 初始化失败: {server_name}",
                    details=[f"server_name={server_name}", str(exc)],
                )
                raise
            server_tools[server_name] = tools
            self._log_execution(
                session,
                "info",
                "mcp_server_ready",
                f"MCP server 已就绪: {server_name}",
                details=[f"tool_count={len(tools)}"],
            )
        session["mcp_tools"] = server_tools
        self._log_execution(
            session,
            "info",
            "mcp_tooling_ready",
            "MCP 工具注册完成。",
            details=[f"server_count={len(server_tools)}"],
        )
        self._persist_session(session)

    def _mcp_server_config(self, server_name: str, session) -> dict[str, object]:
        module_name = f"app.services.lottery.mcp_servers.{server_name}"
        return {
            "server_name": server_name,
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", module_name],
            "env": self._mcp_env(session),
        }

    def _mcp_env(self, session) -> dict[str, str]:
        backend_root = Path(__file__).resolve().parents[3]
        current = dict(os.environ)
        pythonpath = [str(backend_root)]
        existing = current.get("PYTHONPATH", "").strip()
        if existing:
            pythonpath.append(existing)
        current.update(
            {
                "PYTHONPATH": os.pathsep.join(pythonpath),
                "LOTTERY_WORLD_SESSION_ID": str(session["session_id"]),
                "LOTTERY_WORLD_STATE_ROOT": str(self.store.root),
                "LOTTERY_DATA_ROOT": str(backend_root.parent / "ziweidoushu"),
            }
        )
        if self.kuzu_graph_service is not None:
            current["KUZU_GRAPH_ROOT"] = str(self.kuzu_graph_service.db_root)
        return current

    def _ensure_agents(self, session, strategies, context) -> None:
        if session["agents"]:
            return
        refs = [_strategy_ref(strategy) for strategy in strategies.values()]
        refs.extend(_market_role_refs(session))
        refs.extend(_world_refs())
        session["agents"], session["agent_state"] = [], {}
        rows = _parallel_results(refs, min(len(refs), 6), lambda ref: self._register_agent_payload(session, ref, context))
        events = []
        for agent_row, state_row, event in rows:
            session["agents"].append(agent_row)
            session["agent_state"][agent_row["session_agent_id"]] = state_row
            self._attach_agent_tools(session, agent_row)
            events.append(event)
        session["active_agent_ids"] = [item["session_agent_id"] for item in session["agents"]]
        self._append_events(session, events)
        self._sync_shared_blocks(session, session["active_agent_ids"])
        self._persist_session(session)

    def _register_agent_payload(self, session, ref, context):
        bankroll = ""
        if ref.group in {"purchase", "bettor"}:
            bankroll = f"Budget {session['budget_yuan']} yuan. State tradeoffs and payoff target clearly."
        prompt_passages = _agent_prompt_passages(ref, context)
        prompt_docs = _bound_prompt_docs(ref)
        letta_id = self._create_agent(
            session,
            ref.session_agent_id,
            ref.description,
            agent_blocks(ref.display_name, ref.description, bankroll),
            {"group": ref.group, "role_kind": ref.role_kind},
        )
        agent_row = {**ref.to_dict(), "letta_agent_id": letta_id}
        state_row = {
            "display_name": ref.display_name,
            "persona": ref.description,
            "group": ref.group,
            "role_kind": ref.role_kind,
            "trust_network": [],
            "post_history": [],
            "revision_history": [],
            "recent_hits": [],
            "last_phase": "idle",
            "last_numbers": [],
            "last_comment": "",
            "bound_prompt_docs": prompt_docs,
            "bound_prompt_passage_count": len(prompt_passages),
        }
        for text in prompt_passages:
            self._add_passage(session, letta_id, text, ["lottery", "prompt"])
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            session.get("current_phase") or "idle",
            "agent_registered",
            ref.session_agent_id,
            ref.display_name,
            f"role={ref.role_kind}, group={ref.group}",
            metadata={
                "group": ref.group,
                "role_kind": ref.role_kind,
                "bound_prompt_docs": prompt_docs,
                "bound_prompt_passage_count": len(prompt_passages),
            },
        )
        return agent_row, state_row, event

    def _attach_agent_tools(self, session, agent_row: dict[str, Any]) -> None:
        if self._mcp_disabled_mode():
            return
        role_kind = str(agent_row.get("role_kind", "")).strip()
        group = str(agent_row.get("group", "")).strip()
        if not role_kind:
            return
        tool_cache = session.get("mcp_tools", {})
        attached = {
            str(item.get("id", "")).strip()
            for item in self._client(session).list_tools_for_agent(agent_row["letta_agent_id"])
            if str(item.get("id", "")).strip()
        }
        for server_name, tool_map in tool_cache.items():
            for tool_name, tool_id in tool_map.items():
                if tool_id in attached:
                    continue
                if not _tool_role_matches(server_name, tool_name, role_kind, group):
                    continue
                self._client(session).attach_tool_to_agent(agent_row["letta_agent_id"], tool_id)
                attached.add(tool_id)
        if role_kind in {"social", "judge", "bettor", "purchase", "analyst"} and not attached:
            raise ValueError(
                f"No MCP tools attached for {agent_row.get('session_agent_id', role_kind)} ({role_kind}/{group})"
            )

    def _social_posts(
        self,
        session,
        context,
        signal_outputs,
        performance,
        dialogue_enabled: bool,
        dialogue_rounds: int,
    ) -> list[WorldEvent]:
        agent_ids = [
            item["session_agent_id"]
            for item in session["agents"]
            if item.get("group") == "social"
        ]
        if not agent_ids:
            return []
        round_count = max(1, dialogue_rounds if dialogue_enabled else 1)
        session["progress"]["dialogue_round_total"] = round_count
        events: list[WorldEvent] = []
        for round_index in range(1, round_count + 1):
            session["progress"]["dialogue_round_index"] = round_index
            self._persist_session(session)
            events.extend(
                _parallel_results(
                    agent_ids,
                    min(len(agent_ids), 4),
                    lambda agent_id: self._social_post(
                        session,
                        context,
                        signal_outputs,
                        performance,
                        events,
                        round_index,
                        agent_id,
                    ),
                )
            )
        return events

    def _social_post(
        self,
        session,
        context,
        signal_outputs,
        performance,
        prior_events: list[WorldEvent],
        round_index: int,
        agent_id: str,
    ) -> WorldEvent:
        agent = _agent_by_id(session, agent_id)
        session["progress"]["current_actor_id"] = agent_id
        session["progress"]["current_actor_name"] = agent["display_name"]
        self._persist_session(session)
        strategy_groups = _strategy_group_lookup(session)
        view = build_social_prompt_view(
            agent_id,
            signal_outputs,
            prior_events,
            performance,
            strategy_groups,
        )
        prompt = "\n".join(
            [
                session["shared_memory"]["current_issue"],
                f"Social round: {round_index}",
                f"Visible signal board:\n{view['signal_board']}",
                f"Visible leaderboard:\n{view['leaderboard']}",
                f"Market focus:\n{view['market_focus']}",
                f"Execution note:\n{view['instruction']}",
                f"Recent social posts:\n{_recent_phase_summary(prior_events, 'social_propagation')}",
                f"Recent interviews:\n{_recent_phase_summary(prior_events, 'public_debate')}",
                (
                    'Return JSON only: {"comment":"...", "focus":["..."], '
                    '"trusted_strategy_ids":["..."], "highlighted_numbers":[...], '
                    '"support_agent_ids":["..."], "sentiment":"bullish|mixed|defensive"}'
                ),
            ]
        )
        cached = self._load_cached_agent_result(session, agent_id, prompt)
        if cached is None:
            payload = parse_json_response(self._send_message(session, agent["letta_agent_id"], prompt))
            self._save_cached_agent_result(session, agent_id, prompt, payload)
        else:
            payload = cached
        numbers = [int(value) for value in payload.get("highlighted_numbers", []) if str(value).strip()][:8]
        state = session["agent_state"][agent_id]
        trust_ids = [str(value) for value in payload.get("trusted_strategy_ids", []) if str(value).strip()]
        for value in trust_ids:
            if value not in state["trust_network"]:
                state["trust_network"].append(value)
        event = self._event(
            session["session_id"],
            context.target_draw.period,
            "social_propagation",
            "social_post",
            agent_id,
            agent["display_name"],
            str(payload.get("comment", "")).strip(),
            tuple(numbers),
            {
                "group": "social",
                "round": round_index,
                "focus": payload.get("focus", []),
                "trusted_strategy_ids": trust_ids,
                "support_agent_ids": payload.get("support_agent_ids", []),
                "highlighted_numbers": numbers,
                "sentiment": str(payload.get("sentiment", "mixed")).strip() or "mixed",
            },
        )
        _record_agent_activity(state, context.target_draw.period, "social_propagation", event.content, numbers)
        return event

    def _judge_boards(self, session, signal_outputs, social_posts, leaderboard, parallelism: int) -> list[WorldEvent]:
        judge_ids = [
            item["session_agent_id"]
            for item in session["agents"]
            if item.get("group") == "judge"
        ]
        if not judge_ids:
            return []
        session["progress"]["dialogue_round_index"] = 1
        session["progress"]["dialogue_round_total"] = max(
            int(session["progress"].get("dialogue_round_total", 0) or 0),
            1,
        )
        return _parallel_results(
            judge_ids,
            min(len(judge_ids), max(parallelism, 1)),
            lambda agent_id: self._judge_board_event(session, signal_outputs, social_posts, leaderboard, agent_id),
        )

    def _judge_board_event(self, session, signal_outputs, social_posts, leaderboard, agent_id: str) -> WorldEvent:
        agent = _agent_by_id(session, agent_id)
        session["progress"]["current_actor_id"] = agent_id
        session["progress"]["current_actor_name"] = agent["display_name"]
        self._persist_session(session)
        prompt = "\n".join(
            [
                session["shared_memory"]["current_issue"],
                f"Signal board:\n{_signal_output_block(signal_outputs)}",
                f"Social feed:\n{_event_digest_block(social_posts)}",
                f"Leaderboard:\n{_performance_block(_leaderboard_performance(leaderboard))}",
                (
                    'Return JSON only: {"numbers":[...], "comment":"...", "rationale":"...", '
                    '"trusted_strategy_ids":["..."], "play_size_bias":<int or null>, '
                    '"structure_bias":"tickets|wheel|dan_tuo|portfolio"}'
                ),
            ]
        )
        cached = self._load_cached_agent_result(session, agent_id, prompt)
        if cached is None:
            payload = parse_json_response(self._send_message(session, agent["letta_agent_id"], prompt))
            self._save_cached_agent_result(session, agent_id, prompt, payload)
        else:
            payload = cached
        numbers = [int(value) for value in payload.get("numbers", []) if str(value).strip()][:10]
        _record_agent_activity(session["agent_state"][agent_id], session.get("current_period") or "-", "market_rerank", str(payload.get("rationale", "")).strip(), numbers)
        return self._event(
            session["session_id"],
            session.get("current_period") or "-",
            "market_rerank",
            "market_rank",
            agent_id,
            agent["display_name"],
            str(payload.get("comment", "")).strip() or str(payload.get("rationale", "")).strip(),
            tuple(numbers),
            {
                "group": "judge",
                "trusted_strategy_ids": payload.get("trusted_strategy_ids", []),
                "play_size_bias": payload.get("play_size_bias"),
                "structure_bias": payload.get("structure_bias", "tickets"),
                "rationale": str(payload.get("rationale", "")).strip(),
            },
        )

    def _bettor_market_plans(
        self,
        session,
        period: str,
        signal_outputs,
        social_posts,
        market_ranks,
        parallelism: int,
    ) -> tuple[list[WorldEvent], dict[str, dict[str, object]]]:
        bettor_ids = [
            item["session_agent_id"]
            for item in session["agents"]
            if item.get("group") == "bettor"
        ]
        if not bettor_ids:
            return [], {}
        results = _parallel_results(
            bettor_ids,
            min(len(bettor_ids), max(parallelism, 1)),
            lambda agent_id: self._bettor_plan_result(
                session,
                period,
                signal_outputs,
                social_posts,
                market_ranks,
                agent_id,
            ),
        )
        events = []
        payload = {}
        for result in results:
            if not result["ok"]:
                agent_id = result["agent_id"]
                state = session["agent_state"].get(agent_id, {})
                state["last_error"] = {
                    "phase": "bettor_planning",
                    "period": period,
                    "message": result["error"],
                }
                self._log_execution(
                    session,
                    "warning",
                    "bettor_plan_invalid",
                    f"跳过无效的 bettor 计划: {result['display_name']}",
                    phase="bettor_planning",
                    details=[f"agent_id={agent_id}", result["error"]],
                )
                events.append(
                    self._event(
                        session["session_id"],
                        period,
                        "bettor_planning",
                        "bet_plan_failed",
                        agent_id,
                        result["display_name"],
                        result["error"],
                        (),
                        {"group": "bettor", "status": "failed"},
                    )
                )
                continue
            plan, event = result["plan"], result["event"]
            payload[plan["role_id"]] = plan
            events.append(event)
        if not payload:
            raise ValueError("world_v2_market requires at least one valid bettor plan before synthesis")
        return events, payload

    def _bettor_plan_result(self, session, period: str, signal_outputs, social_posts, market_ranks, agent_id: str):
        agent = _agent_by_id(session, agent_id)
        try:
            plan, event = self._bettor_plan(session, period, signal_outputs, social_posts, market_ranks, agent_id)
        except Exception as exc:
            return {
                "ok": False,
                "agent_id": agent_id,
                "display_name": agent["display_name"],
                "error": str(exc).strip() or exc.__class__.__name__,
            }
        return {"ok": True, "plan": plan, "event": event}

    def _bettor_plan(self, session, period: str, signal_outputs, social_posts, market_ranks, agent_id: str):
        agent = _agent_by_id(session, agent_id)
        persona_budget = int(agent.get("metadata", {}).get("budget_yuan", session["budget_yuan"]) or session["budget_yuan"])
        max_tickets = max(persona_budget // TICKET_COST_YUAN, 1)
        strategy_groups = _strategy_group_lookup(session)
        view = build_bettor_prompt_view(
            agent_id,
            signal_outputs,
            social_posts,
            market_ranks,
            strategy_groups,
        )
        prompt = "\n".join(
            [
                session["shared_memory"]["current_issue"],
                f"Your persona budget: {persona_budget} yuan.",
                f"Visible signal board:\n{view['signal_board']}",
                f"Visible social feed:\n{view['social_feed']}",
                f"Visible judge boards:\n{view['judge_boards']}",
                f"Market focus:\n{view['market_focus']}",
                f"Persona execution note:\n{view['instruction']}",
                _bettor_prompt_assets(agent, session),
                purchase_rule_block(),
                *_plan_guard_lines(persona_budget, max_tickets),
                "Return one executable betting plan that fits your persona and budget.",
                purchase_schema(),
            ]
        )
        raw = self._send_message(session, agent["letta_agent_id"], prompt)
        proposal = _purchase_json(agent_id, raw)
        try:
            structure = planner_structure(proposal, session["pick_size"], max_tickets)
            plan = bet_plan_from_payload(agent_id, proposal, structure)
            serialized = serialize_bet_plan(plan, proposal, structure, agent["display_name"])
        except Exception as exc:
            raise ValueError(f"{agent_id} returned invalid betting plan: {raw}") from exc
        serialized["budget_yuan"] = persona_budget
        serialized["status"] = "ready"
        serialized["period"] = period
        serialized["game"] = "Happy 8"
        serialized["ticket_cost_yuan"] = TICKET_COST_YUAN
        state = session["agent_state"][agent_id]
        _record_agent_activity(
            state,
            period,
            "bettor_planning",
            serialized.get("rationale", ""),
            serialized.get("legs", [{}])[0].get("numbers", []),
        )
        event = self._event(
            session["session_id"],
            period,
            "bettor_planning",
            "bet_plan",
            agent_id,
            agent["display_name"],
            serialized.get("rationale", ""),
            tuple(reference_leg_payload(serialized)["numbers"]),
            {
                "group": "bettor",
                "plan_type": serialized.get("plan_type"),
                "play_size": serialized.get("play_size"),
                "risk_exposure": serialized.get("risk_exposure"),
            },
        )
        return serialized, event

    def _synthesize_market(self, session, signal_outputs, social_posts, market_ranks):
        chair = _agent_by_id(session, "purchase_chair")
        prompt = "\n".join(
            [
                session["shared_memory"]["current_issue"],
                f"Signal board:\n{_signal_output_block(signal_outputs)}",
                f"Social feed:\n{_event_digest_block(social_posts)}",
                f"Judge boards:\n{_event_digest_block(market_ranks)}",
                purchase_rule_block(),
                f"Global budget cap: {_session_budget(session)} yuan.",
                *_plan_guard_lines(_session_budget(session), _session_max_tickets(session)),
                "Choose one reference plan for the market and keep it executable under the global budget.",
                purchase_schema(),
            ]
        )
        cached = self._load_cached_agent_result(session, "purchase_chair", prompt)
        if cached is None:
            proposal, structure = self._resolve_purchase_chair_plan(
                session,
                chair,
                prompt,
                phase="plan_synthesis",
            )
            plan = bet_plan_from_payload("purchase_chair", proposal, structure)
            final_plan = serialize_bet_plan(plan, proposal, structure, chair["display_name"])
            self._save_cached_agent_result(
                session,
                "purchase_chair",
                prompt,
                {
                    "proposal": proposal,
                    "final_plan": final_plan,
                    "rationale": plan.rationale,
                },
            )
        else:
            proposal = dict(cached["proposal"])
            structure = planner_structure(proposal, session["pick_size"], _session_max_tickets(session))
            final_plan = dict(cached["final_plan"])
            plan = bet_plan_from_payload("purchase_chair", proposal, structure)
        final_plan.update(
            {
                "status": "ready",
                "period": session.get("current_period"),
                "game": "Happy 8",
                "budget_yuan": _session_budget(session),
                "ticket_cost_yuan": TICKET_COST_YUAN,
            }
        )
        synthesis = market_synthesis_payload(
            signal_outputs=[serialize_signal_output(item) for item in signal_outputs],
            social_posts=[item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in social_posts],
            judge_boards=[item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in market_ranks],
            bet_plans={},
            reference_plan_id="purchase_chair",
            reference_plan=final_plan,
            rationale=plan.rationale,
        )
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            "plan_synthesis",
            "purchase_decision",
            "purchase_chair",
            chair["display_name"],
            plan.rationale,
            tuple(reference_leg_payload(final_plan)["numbers"]),
            {
                "group": "purchase",
                "plan_type": final_plan.get("plan_type"),
                "play_size": final_plan.get("play_size"),
            },
        )
        _record_agent_activity(
            session["agent_state"]["purchase_chair"],
            session.get("current_period") or "-",
            "plan_synthesis",
            plan.rationale,
            reference_leg_payload(final_plan)["numbers"],
        )
        return synthesis, final_plan, event

    def _handbook_final_decision(
        self,
        session,
        period: str,
        signal_outputs,
        social_posts,
        market_ranks,
        final_plan,
        leaderboard,
    ) -> tuple[dict[str, Any], WorldEvent]:
        agent = _agent_by_id(session, "handbook_decider")
        prompt = "\n".join(
            [
                session["shared_memory"]["current_issue"],
                f"Target issue: {period}",
                f"Generator boards:\n{_signal_output_block(signal_outputs)}",
                f"Social feed:\n{_event_digest_block(social_posts)}",
                f"Judge boards:\n{_event_digest_block(market_ranks)}",
                f"Purchase recommendation:\n{_purchase_recommendation_block(final_plan)}",
                f"Leaderboard:\n{_performance_block(_leaderboard_performance(leaderboard))}",
                f"Recent review:\n{_review_block(session.get('latest_review', {}))}",
                (
                    'Return JSON only: {"numbers":[...], "alternate_numbers":[...], '
                    '"trusted_strategy_ids":["..."], "adopted_groups":["..."], '
                    '"accepted_purchase_recommendation":true, "rationale":"...", "risk_note":"..."}'
                ),
            ]
        )
        cached = self._load_cached_agent_result(session, "handbook_decider", prompt)
        if cached is None:
            payload = parse_json_response(self._send_message(session, agent["letta_agent_id"], prompt))
            self._save_cached_agent_result(session, "handbook_decider", prompt, payload)
        else:
            payload = cached
        numbers = [int(value) for value in payload.get("numbers", []) if str(value).strip()][: session["pick_size"]]
        if len(numbers) != session["pick_size"]:
            raise ValueError(f"handbook_decider returned invalid official numbers: {payload}")
        alternates = [int(value) for value in payload.get("alternate_numbers", []) if str(value).strip()][:3]
        final_decision = {
            "period": period,
            "numbers": numbers,
            "alternate_numbers": alternates,
            "trusted_strategy_ids": [str(value) for value in payload.get("trusted_strategy_ids", []) if str(value).strip()],
            "adopted_groups": [str(value) for value in payload.get("adopted_groups", []) if str(value).strip()],
            "accepted_purchase_recommendation": bool(payload.get("accepted_purchase_recommendation", False)),
            "rationale": str(payload.get("rationale", "")).strip(),
            "risk_note": str(payload.get("risk_note", "")).strip(),
            "purchase_reference_numbers": reference_leg_payload(final_plan)["numbers"],
        }
        _record_agent_activity(
            session["agent_state"]["handbook_decider"],
            period,
            "handbook_final_decision",
            final_decision["rationale"],
            final_decision["numbers"],
        )
        event = self._event(
            session["session_id"],
            period,
            "handbook_final_decision",
            "official_prediction",
            "handbook_decider",
            agent["display_name"],
            final_decision["rationale"],
            tuple(numbers),
            {
                "group": "decision",
                "alternate_numbers": alternates,
                "trusted_strategy_ids": final_decision["trusted_strategy_ids"],
                "adopted_groups": final_decision["adopted_groups"],
                "accepted_purchase_recommendation": final_decision["accepted_purchase_recommendation"],
                "risk_note": final_decision["risk_note"],
            },
        )
        return final_decision, event

    def _resolve_purchase_chair_plan(self, session, chair, prompt: str, *, phase: str):
        raw = ""
        last_error = None
        for attempt in range(1, PURCHASE_PLAN_REPAIR_ATTEMPTS + 1):
            request_prompt = prompt if attempt == 1 else _purchase_repair_prompt(prompt, raw, last_error)
            raw = self._send_message(session, chair["letta_agent_id"], request_prompt)
            try:
                proposal = _purchase_json("purchase_chair", raw)
                structure = planner_structure(proposal, session["pick_size"], _session_max_tickets(session))
            except Exception as exc:
                last_error = exc
                self._log_execution(
                    session,
                    "warning",
                    "purchase_plan_invalid_attempt",
                    f"purchase_chair plan validation failed (attempt {attempt}/{PURCHASE_PLAN_REPAIR_ATTEMPTS})",
                    phase=phase,
                    details=_purchase_validation_details(exc, raw),
                )
                continue
            if attempt > 1:
                self._log_execution(
                    session,
                    "info",
                    "purchase_plan_repaired",
                    "purchase_chair returned a corrected executable plan after validation feedback.",
                    phase=phase,
                )
            return proposal, structure
        raise ValueError(f"purchase_chair returned invalid purchase plan: {raw}") from last_error

    def _update_shared_memory(self, session, context, predictions, performance) -> None:
        shared = session["shared_memory"]
        issue_text = issue_block(context, predictions, performance)
        shared["current_issue"] = issue_text
        all_docs = session.get("_all_documents")
        shared["visible_draw_history_digest"] = _visible_draw_history_digest(context.history_draws)
        shared["market_board"] = _generator_market_board(predictions, performance)
        shared["social_feed"] = NO_SOCIAL_FEED
        shared["purchase_board"] = NO_PURCHASE_BOARD
        shared["handbook_principles"] = _handbook_principles_block(all_docs)
        shared["final_decision_constraints"] = _final_decision_constraints_block(
            session,
            context.target_draw.period,
        )
        shared["report_digest"] = report_digest(context, all_documents=all_docs)
        shared["rule_digest"] = rule_digest(predictions, performance)
        shared["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        session.setdefault("current_round", {})["issue_base"] = issue_text
        self._sync_shared_blocks(session)

    def _refresh_social_feed_block(self, session, social_posts) -> None:
        session["shared_memory"]["social_feed"] = _social_feed_memory_block(social_posts)
        self._sync_shared_blocks(session)

    def _refresh_market_board_block(
        self,
        session,
        signal_outputs,
        social_posts,
        market_ranks,
        leaderboard,
    ) -> None:
        session["shared_memory"]["market_board"] = _market_board_memory_block(
            signal_outputs,
            social_posts,
            market_ranks,
            leaderboard,
        )
        self._sync_shared_blocks(session)

    def _refresh_purchase_board_block(self, session, final_plan: dict[str, Any]) -> None:
        session["shared_memory"]["purchase_board"] = _purchase_board_memory_block(final_plan)
        self._sync_shared_blocks(session)

    def _refresh_round_cache_context(self, session, round_state, assets, target_issue: str, options) -> None:
        round_state["cache_context"] = {
            "target_issue": target_issue,
            "visible_history_hash": _visible_history_hash(assets.completed_draws),
            "config_hash": _runtime_config_hash(session, options),
        }
        round_state["runtime_config"] = _round_runtime_config(session, options)
        round_state["participant_agents"] = _participant_agents_snapshot(session)

    def _load_cached_agent_result(
        self,
        session,
        agent_id: str,
        prompt: str,
    ) -> dict[str, Any] | None:
        cache_key = self._agent_result_cache_key(session, agent_id, prompt)
        if cache_key is None:
            return None
        cached = self.store.load_result_cache(cache_key)
        if cached is None:
            self._increment_request_metric(session, "result_cache_miss")
            return None
        self._increment_request_metric(session, "result_cache_hit")
        return dict(cached.get("payload") or {})

    def _save_cached_agent_result(
        self,
        session,
        agent_id: str,
        prompt: str,
        payload: dict[str, Any],
    ) -> None:
        cache_key = self._agent_result_cache_key(session, agent_id, prompt)
        if cache_key is None:
            return
        target_issue, logical_agent_id, visible_history_hash, prompt_hash, config_hash = cache_key
        self.store.save_result_cache(
            cache_key,
            {
                "cached_at": world_now(),
                "target_issue": target_issue,
                "agent_id": logical_agent_id,
                "visible_history_hash": visible_history_hash,
                "prompt_hash": prompt_hash,
                "config_hash": config_hash,
                "payload": payload,
            },
        )

    def _agent_result_cache_key(
        self,
        session,
        agent_id: str,
        prompt: str,
    ) -> tuple[str, str, str, str, str] | None:
        round_state = dict(session.get("current_round", {}))
        cache_context = dict(round_state.get("cache_context", {}))
        target_issue = str(cache_context.get("target_issue", "")).strip()
        visible_history_hash = str(cache_context.get("visible_history_hash", "")).strip()
        config_hash = str(cache_context.get("config_hash", "")).strip()
        if not target_issue or not visible_history_hash or not config_hash:
            return None
        logical_agent_id = _session_agent_id(session, agent_id)
        prompt_hash = _stable_hash(prompt)
        return (
            target_issue,
            logical_agent_id,
            visible_history_hash,
            prompt_hash,
            config_hash,
        )

    def _sync_shared_blocks(self, session, agent_ids: Iterable[str] | None = None) -> None:
        cache = session.setdefault("_shared_block_cache", {})
        allowed = set(agent_ids or [])
        for agent in session["agents"]:
            if allowed and agent["session_agent_id"] not in allowed:
                continue
            agent_cache = cache.setdefault(agent["session_agent_id"], {})
            for label in SHARED_BLOCKS:
                value = session["shared_memory"][label]
                if agent_cache.get(label) == value:
                    continue
                self._update_block(session, agent["letta_agent_id"], label, value)
                agent_cache[label] = value

    def _project_runtime_market(self, session) -> None:
        if self.kuzu_graph_service is None:
            return
        self.kuzu_graph_service.project_runtime_state(session)

    def _mark_runtime_projection_dirty(self, session) -> None:
        if self.kuzu_graph_service is None:
            return
        session["_runtime_projection_dirty"] = True

    def _flush_runtime_projection(self, session) -> None:
        if not session.get("_runtime_projection_dirty"):
            return
        self._project_runtime_market(session)
        session["_runtime_projection_dirty"] = False

    def _opening_events(self, session, period, predictions) -> list[WorldEvent]:
        rows = []
        for strategy_id, prediction in predictions.items():
            state = _agent_state_row(session, strategy_id, prediction.display_name, prediction.rationale)
            state["group"] = prediction.group
            state["role_kind"] = prediction.kind
            _record_agent_activity(state, period, "opening", prediction.rationale, prediction.numbers)
            rows.append(
                self._event(
                    session["session_id"],
                    period,
                    "generator_opening",
                    "prediction_post",
                    strategy_id,
                    prediction.display_name,
                    prediction.rationale,
                    tuple(prediction.numbers),
                    {"group": prediction.group, "kind": prediction.kind},
                )
            )
        return rows

    def _commentary(self, session, agent_id, phase, prompt) -> WorldEvent:
        agent = _agent_by_id(session, agent_id)
        payload = parse_json_response(self._send_message(session, agent["letta_agent_id"], prompt))
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            phase,
            "comment",
            agent_id,
            agent["display_name"],
            str(payload.get("comment", "")).strip(),
            metadata={
                "group": agent.get("group", "-"),
                "focus": payload.get("focus", []),
                "trusted_strategy_ids": payload.get("trusted_strategy_ids", []),
            },
        )
        _record_agent_activity(
            session["agent_state"][agent_id],
            session.get("current_period") or "-",
            phase,
            event.content,
            event.numbers,
        )
        return event

    def _interviews(self, session, context, predictions, performance, parallelism: int) -> list[WorldEvent]:
        ordered = sorted(
            [strategy_id for strategy_id in predictions if _session_has_agent(session, strategy_id)],
            key=lambda item: int(performance.get(item, {}).get("rank", 999) or 999),
        )
        interview_ids = ordered[:3]
        if not interview_ids:
            return []
        return _parallel_results(
            interview_ids,
            parallelism,
            lambda strategy_id: self._interview_event(session, context, predictions[strategy_id], performance),
        )

    def _interview_event(self, session, context, prediction, performance) -> WorldEvent:
        question = prediction_prompt(context, prediction, performance)
        answer = (
            self._send_message(session, _agent_by_id(session, prediction.strategy_id)["letta_agent_id"], question)
            if _session_has_agent(session, prediction.strategy_id)
            else _rule_stage_interview(prediction, context.target_draw.period)
        )
        event = self._event(
            session["session_id"],
            context.target_draw.period,
            "social_propagation",
            "live_interview",
            prediction.strategy_id,
            prediction.display_name,
            answer,
            tuple(prediction.numbers),
            {"group": prediction.group, "question": question},
        )
        _record_agent_activity(
            _agent_state_row(session, prediction.strategy_id, prediction.display_name, prediction.rationale),
            context.target_draw.period,
            "social_propagation",
            answer,
            prediction.numbers,
        )
        return event

    def _debate(
        self,
        session,
        context,
        predictions,
        performance,
        pick_size: int,
        dialogue_enabled: bool,
        dialogue_rounds: int,
    ):
        updated = dict(predictions)
        events: list[WorldEvent] = []
        round_count = max(1, dialogue_rounds if dialogue_enabled else 1)
        active_agents = _active_agents(session, performance)
        for round_index in range(1, round_count + 1):
            round_events = self._debate_round(
                session,
                context,
                active_agents,
                updated,
                pick_size,
                round_index,
                events,
                parallelism=(round_index == 1),
            )
            events.extend(round_events)
            self._append_public_discussion(session, round_events, persist=True)
            summary = self._debate_summary(session, context.target_draw.period, round_index, events)
            if summary is not None:
                events.append(summary)
                self._append_public_discussion(session, [summary], persist=True)
        return updated, events

    def _debate_round(
        self,
        session,
        context,
        active_agents,
        updated,
        pick_size: int,
        round_index: int,
        prior_events: list[WorldEvent],
        parallelism: bool,
    ) -> list[WorldEvent]:
        participants = _follow_up_agents(active_agents, updated, round_index)
        if parallelism:
            snapshot = dict(updated)
            turns = _parallel_results(
                participants,
                min(len(participants), 6),
                lambda agent: self._debate_turn(
                    session,
                    context,
                    snapshot,
                    agent,
                    pick_size,
                    round_index,
                    prior_events,
                ),
            )
        else:
            turns = []
            for agent in participants:
                turns.append(
                    self._debate_turn(
                        session,
                        context,
                        updated,
                        agent,
                        pick_size,
                        round_index,
                        prior_events,
                    )
                )
        events = []
        for strategy_id, prediction, support_ids, event in turns:
            updated[strategy_id] = prediction
            self._apply_debate_activity(session, context.target_draw.period, strategy_id, prediction, support_ids, event, round_index)
            events.append(event)
        return events

    def _debate_turn(
        self,
        session,
        context,
        predictions,
        agent,
        pick_size: int,
        round_index: int,
        prior_events: list[WorldEvent],
    ):
        strategy_id = agent["session_agent_id"]
        previous = predictions[strategy_id]
        prompt = (
            f"{session['shared_memory']['current_issue']}\n\n"
            f"Debate round: {round_index}\n"
            f"Latest strategy numbers:\n{_debate_snapshot(predictions, strategy_id)}\n"
            f"Latest debate posts:\n{_recent_phase_summary(prior_events, 'public_debate')}\n\n"
            f"Reply publicly, cite peers if needed, then revise your {pick_size} numbers if needed.\n{debate_schema(pick_size)}"
        )
        payload = parse_json_response(self._send_message(session, agent["letta_agent_id"], prompt))
        numbers = tuple(int(value) for value in payload.get("numbers", [])[:pick_size])
        next_prediction = previous
        if len(numbers) == pick_size:
            next_prediction = replace(
                previous,
                numbers=numbers,
                rationale=str(payload.get("rationale", previous.rationale)).strip(),
            )
        support_ids = [str(value) for value in payload.get("support_agent_ids", [])]
        event = self._event(
            session["session_id"],
            context.target_draw.period,
            "public_debate",
            "debate_post",
            strategy_id,
            agent["display_name"],
            str(payload.get("comment", "")).strip(),
            numbers,
            {"group": agent.get("group", "-"), "support_agent_ids": support_ids, "round": round_index},
        )
        return strategy_id, next_prediction, support_ids, event

    def _apply_debate_activity(
        self,
        session,
        period: str,
        strategy_id: str,
        prediction,
        support_ids: list[str],
        event: WorldEvent,
        round_index: int,
    ) -> None:
        state = session["agent_state"][strategy_id]
        state["revision_history"].append(
            {"period": period, "round": round_index, "numbers_after": list(prediction.numbers)}
        )
        trust = state["trust_network"]
        trust.extend(value for value in support_ids if value not in trust)
        _record_agent_activity(state, period, "public_debate", event.content, event.numbers or prediction.numbers)

    def _debate_summary(self, session, period: str, round_index: int, events: list[WorldEvent]) -> WorldEvent | None:
        content = _debate_summary_text(events, round_index)
        if not content:
            return None
        event = self._event(
            session["session_id"],
            period,
            "public_debate",
            "debate_summary",
            "world_runtime",
            "World Runtime",
            content,
            metadata={"group": "system", "round": round_index},
        )
        return event

    def _legacy_judge(self, session, round_state, predictions, leaderboard) -> dict[str, Any]:
        contributors = _world_contributors(leaderboard, predictions)
        breakdown = contributor_breakdown(predictions, contributors)
        primary = ensemble_numbers(breakdown, session["pick_size"])
        alternate = ensure_alternate_numbers(primary, alternate_numbers(breakdown, session["pick_size"]))
        alternate = _supplement_alternate_numbers(primary, alternate, predictions, round_state)
        if len(primary) != 5 or len(alternate) != 3:
            raise ValueError(
                f"World synthesis produced invalid compatibility projection: primary={primary}, alternate={alternate}"
            )
        return {
            "primary_numbers": tuple(primary),
            "alternate_numbers": tuple(alternate),
            "trusted_strategy_ids": [item["strategy_id"] for item in contributors[:5]],
            "rationale": _judge_rationale(primary, alternate, breakdown, contributors),
            "focus": [str(number) for number in primary[:3]],
            "strategy_numbers": {strategy_id: list(prediction.numbers) for strategy_id, prediction in predictions.items()},
        }

    def _legacy_purchase(self, session, period: str, judge, actual_numbers, parallelism: int):
        budget_yuan = _session_budget(session)
        max_tickets = _session_max_tickets(session)
        events: list[WorldEvent] = []
        trace: list[dict[str, Any]] = []
        proposals: dict[str, dict[str, Any]] = {}
        for proposal in self._legacy_purchase_round(session, judge, 1, proposals, parallelism):
            proposals[proposal["role_id"]] = proposal
            trace.append(_purchase_trace_row(1, proposal))
            events.append(_purchase_event(session["session_id"], period, proposal, 1))
        session["latest_purchase_plan"] = {
            "status": "discussing",
            "period": period,
            "budget_yuan": budget_yuan,
            "discussion_agents": list(proposals.values()),
            "discussion_trace": list(trace),
        }
        self._persist_session(session)
        for proposal in self._legacy_purchase_round(session, judge, 2, proposals, 1):
            proposals[proposal["role_id"]] = proposal
            trace.append(_purchase_trace_row(2, proposal))
            events.append(_purchase_event(session["session_id"], period, proposal, 2))
        session["latest_purchase_plan"] = {
            "status": "deliberated",
            "period": period,
            "budget_yuan": budget_yuan,
            "discussion_agents": list(proposals.values()),
            "discussion_trace": list(trace),
        }
        self._persist_session(session)
        chair_prompt = (
            f"{session['shared_memory']['current_issue']}\n\n"
            f"Fixed primary numbers: {list(judge['primary_numbers'])}\n"
            f"Fixed alternate numbers: {list(judge['alternate_numbers'])}\n"
            f"Judge rationale: {judge.get('rationale', '')}\n"
            f"Committee discussion:\n{_purchase_committee_summary(proposals.values())}\n"
            f"{purchase_rule_block()}\n"
            "You may return a mixed portfolio that combines multiple structures and play sizes if total cost stays within budget.\n"
            "Do not default to single-ticket plans unless you clearly justify why that dominates tickets/wheel/dan_tuo in the other play sizes.\n"
            f"Return the final {budget_yuan}-yuan plan.\n{purchase_schema()}"
        )
        chair = _agent_by_id(session, "purchase_chair")
        planner, structure = self._resolve_purchase_chair_plan(
            session,
            chair,
            chair_prompt,
            phase="purchase_committee",
        )
        payout = _purchase_payout(structure.tickets, actual_numbers)
        planner_payload = {**planner, "display_name": "LLM-Purchase-Chair", "model": "letta"}
        plan = {
            "status": "ready",
            "period": period,
            "game": "Happy 8",
            "budget_yuan": budget_yuan,
            "ticket_cost_yuan": TICKET_COST_YUAN,
            "ticket_count": len(structure.tickets),
            "total_cost_yuan": len(structure.tickets) * TICKET_COST_YUAN,
            "primary_prediction": list(judge["primary_numbers"]),
            "alternate_numbers": list(judge["alternate_numbers"]),
            "discussion_agents": list(proposals.values()),
            "discussion_trace": trace,
            "planner": planner_payload,
            "plan_type": structure.plan_type,
            "play_size": structure.play_size,
            "play_size_review": planner.get("play_size_review", {}),
            "chosen_edge": planner.get("chosen_edge", ""),
            "plan_structure": dict(structure.summary) | {"primary_ticket": list(judge["primary_numbers"])},
            "tickets": [
                {"index": index, "numbers": list(ticket), "unit_cost_yuan": TICKET_COST_YUAN}
                for index, ticket in enumerate(structure.tickets, start=1)
            ],
            "total_payout": payout,
        }
        _record_agent_activity(
            session["agent_state"]["purchase_chair"],
            period,
            "purchase_committee",
            str(planner.get("rationale", "")).strip(),
            planner.get("primary_ticket", []) or judge["primary_numbers"],
        )
        events.append(
            self._event(
                session["session_id"],
                period,
                "purchase_committee",
                "purchase_decision",
                "purchase_chair",
                "LLM-Purchase-Chair",
                str(planner.get("rationale", "")).strip(),
                tuple(planner.get("primary_ticket", []) or judge["primary_numbers"]),
                {
                    "group": "purchase",
                    "plan_type": planner.get("plan_type", "-"),
                    "play_size": plan["play_size"],
                    "chosen_edge": plan["chosen_edge"],
                },
            )
        )
        session["latest_purchase_plan"] = plan
        return {"plan": plan, "events": events}

    def _legacy_purchase_round(self, session, judge, round_index: int, proposals, parallelism: int):
        refs = list(_purchase_refs())
        summary = _purchase_committee_summary(proposals.values()) if proposals else None
        if round_index == 1 and parallelism > 1:
            return _parallel_results(refs, parallelism, lambda ref: self._legacy_purchase_proposal(session, judge, summary, ref))
        rows = []
        for ref in refs:
            live_summary = _purchase_committee_summary(proposals.values()) if proposals else summary
            proposal = self._legacy_purchase_proposal(session, judge, live_summary, ref)
            proposals[proposal["role_id"]] = proposal
            rows.append(proposal)
        return rows

    def _legacy_purchase_proposal(self, session, judge, summary, ref: WorldAgentRef):
        prompt = _purchase_prompt(session["shared_memory"]["current_issue"], judge, summary, _session_budget(session))
        raw = self._send_message(session, _agent_by_id(session, ref.session_agent_id)["letta_agent_id"], prompt)
        payload = _purchase_json(ref.session_agent_id, raw)
        proposal = _purchase_payload(ref, payload, prompt, raw)
        _record_agent_activity(
            session["agent_state"][ref.session_agent_id],
            session.get("current_period") or "-",
            "purchase_committee",
            proposal["comment"] or proposal["rationale"],
            _proposal_numbers(proposal),
        )
        return proposal

    def _legacy_settle(self, session, actual_draw, predictions, judge, purchase_plan) -> None:
        actual = set(actual_draw.numbers)
        strategy_issue_results = {}
        hits = {}
        for strategy_id, prediction in predictions.items():
            hit_count = len(actual & set(prediction.numbers))
            hits[strategy_id] = hit_count
            strategy_issue_results[strategy_id] = {
                "period": actual_draw.period,
                "date": actual_draw.date,
                "hits": hit_count,
                "predicted_numbers": list(prediction.numbers),
                "actual_numbers": list(actual_draw.numbers),
                "group": prediction.group,
            }
            state = _agent_state_row(session, strategy_id, prediction.display_name, prediction.rationale)
            state["recent_hits"].append(hit_count)
        best_hits = max(hits.values(), default=0)
        session["settlement_history"].append(
            {
                "period": actual_draw.period,
                "consensus_numbers": list(judge["primary_numbers"]),
                "alternate_numbers": list(judge["alternate_numbers"]),
                "actual_numbers": list(actual_draw.numbers),
                "consensus_hits": len(actual & set(judge["primary_numbers"])),
                "best_hits": best_hits,
                "best_strategy_ids": [sid for sid, value in hits.items() if value == best_hits][:3],
                "purchase_profit": (purchase_plan.get("total_payout") or 0) - purchase_plan.get("total_cost_yuan", 0),
                "strategy_issue_results": strategy_issue_results,
            }
        )
        session["shared_memory"]["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        self._sync_shared_blocks(session)
        self._persist_session(session)

    def _payload(self, session, assets, strategies, pick_size: int, options):
        leaderboard, performance = self._performance(strategies, session, pick_size)
        pending = self._pending_prediction_payload(session, leaderboard, performance)
        latest_target = _pending_target_draw(assets)
        return {
            "dataset": dataset_summary(assets),
            "evaluation": evaluation_summary(
                0,
                0,
                session["pick_size"],
                strategies,
                options.request_delay_ms,
                options.model_name,
                options.retry_count,
                options.retry_backoff_ms,
                options.parallelism,
                options.issue_parallelism,
                True,
                options.agent_dialogue_rounds,
                "embedded_world_context",
                None,
            )
            | {
                "runtime_mode": options.runtime_mode,
                "world_mode": "persistent",
                "target_period": latest_target.period,
                "visible_through_period": session.get("visible_through_period"),
                "live_interview_enabled": options.live_interview_enabled,
                "budget_yuan": options.budget_yuan,
                "world_session_id": session["session_id"],
            },
            "process_trace": _process_trace(session),
            "execution_log": list(session.get("execution_log", [])),
            "leaderboard": leaderboard,
            "pending_prediction": pending,
            "world_session": {
                "session_id": session["session_id"],
                "status": session["status"],
                "budget_yuan": session.get("budget_yuan", DEFAULT_BUDGET_YUAN),
                "current_phase": session["current_phase"],
                "current_period": session.get("current_period"),
                "llm_model_name": session.get("llm_model_name"),
                "active_agent_ids": session.get("active_agent_ids", []),
                "shared_memory": session["shared_memory"],
                "agents": session["agents"],
                "agent_state": session.get("agent_state", {}),
                "progress": session.get("progress", {}),
                "request_metrics": session.get("request_metrics", {}),
                "latest_issue_summary": session.get("latest_issue_summary", {}),
                "latest_purchase_plan": session.get("latest_purchase_plan", {}),
                "latest_review": session.get("latest_review", {}),
                "current_round": session.get("current_round", {}),
                "round_history": session.get("round_history", []),
                "settlement_history": session.get("settlement_history", []),
                "issue_ledger": session.get("issue_ledger", []),
                "visible_through_period": session.get("visible_through_period"),
                "asset_manifest": session.get("asset_manifest", []),
                "failed_phase": session.get("failed_phase"),
                "last_success_phase": session.get("last_success_phase"),
                "manual_reference_documents": [
                    {
                        "name": item.name,
                        "path": item.relative_path,
                        "note": "仅供人工查看，不会进入 agent 输入。",
                    }
                    for item in manual_reference_documents(assets.knowledge_documents)
                ],
                "execution_log": list(session.get("execution_log", [])),
                "error": session.get("error"),
            },
            "report_artifacts": session.get("report_artifacts"),
            "failure": session.get("error"),
        }

    def _pending_prediction_payload(self, session, leaderboard, performance):
        latest = dict(session.get("latest_prediction", {}))
        if not latest:
            return None
        predictions = {item["strategy_id"]: _deserialize_prediction(item) for item in latest.get("strategy_predictions", [])}
        contributors = _world_contributors(leaderboard, predictions)
        breakdown = contributor_breakdown(predictions, contributors) if predictions and contributors else {}
        ensemble = list(latest.get("ensemble_numbers", []))
        return {
            "period": latest.get("period"),
            "date": latest.get("date"),
            "visible_through_period": latest.get("visible_through_period"),
            "predicted_period": latest.get("predicted_period", latest.get("period")),
            "generator_boards": list(latest.get("generator_boards", latest.get("signal_outputs", []))),
            "market_discussion": dict(latest.get("market_discussion", {})),
            "purchase_recommendation": dict(latest.get("purchase_recommendation", latest.get("purchase_plan", {}))),
            "final_decision": dict(latest.get("final_decision", {})),
            "ensemble_numbers": ensemble,
            "alternate_numbers": list(latest.get("alternate_numbers", [])),
            "ensemble_breakdown": ensemble_breakdown(ensemble, breakdown) if breakdown else [],
            "contributors": contributors,
            "performance_context": performance_rows(performance),
            "strategy_predictions": latest.get("strategy_predictions", []),
            "coordination_trace": latest.get("coordination_trace", []),
            "social_state": latest.get("social_state", {}),
            "world_state": latest.get("world_state", {}),
            "latest_review": latest.get("latest_review", session.get("latest_review", {})),
            "world_timeline_preview": self.store.list_events(session["session_id"], 0, 20, latest=True)["items"],
        }

    def _load_round_state(self, session, target_draw) -> dict[str, Any]:
        current = dict(session.get("current_round", {}))
        if current.get("target_period") == target_draw.period:
            return current
        next_round = int(session.get("progress", {}).get("current_round", 0)) + 1
        session["progress"]["current_round"] = next_round
        return {
            "round_id": next_round,
            "target_period": target_draw.period,
            "target_date": target_draw.date,
            "visible_through_period": session.get("visible_through_period"),
            "status": "running",
            "started_at": world_now(),
            "updated_at": world_now(),
        }

    def _save_round_state(self, session, round_state: dict[str, Any]) -> None:
        round_state["updated_at"] = world_now()
        session["current_round"] = round_state
        self._persist_session(session)

    def _can_skip_phase(self, session, phase: str) -> bool:
        if session.get("status") != "failed":
            return True
        failed_phase = session.get("failed_phase")
        if not failed_phase:
            return True
        return ROUND_PHASES.index(phase) < ROUND_PHASES.index(failed_phase)

    def _performance(self, strategies, session, pick_size: int):
        issue_results = {strategy_id: [] for strategy_id in strategies}
        for settlement in session.get("settlement_history", []):
            rows = settlement.get("strategy_issue_results", {})
            for strategy_id, row in rows.items():
                if strategy_id in issue_results:
                    issue_results[strategy_id].append(row)
        leaderboard = build_leaderboard(strategies, issue_results, pick_size) if strategies else []
        performance = build_strategy_performance(leaderboard) if leaderboard else {}
        return leaderboard, performance

    def _sync_asset_manifest(self, session, target_period: str) -> None:
        session["asset_manifest"] = list(build_world_asset_manifest(target_period))
        self._persist_session(session)

    def _create_session_duplicate(
        self,
        strategies,
        pick_size: int,
        model_name: str | None,
        budget_yuan: int,
        session_id: str | None = None,
    ):
        session = WorldSession.create(
            WORLD_V1_RUNTIME_MODE,
            pick_size,
            budget_yuan,
            list(strategies.keys()),
            "尽量中奖，并保留可解释的社交世界决策过程。",
            model_name,
            session_id,
        ).to_dict()
        session["status"] = "idle"
        session["agents"] = []
        session["agent_state"] = {}
        session["request_metrics"] = {
            "create_agent": 0,
            "add_passage": 0,
            "update_block": 0,
            "send_message": 0,
        }
        session["progress"] = {
            "current_round": 0,
            "settled_rounds": 0,
            "awaiting_period": None,
            "dialogue_round_index": 0,
            "dialogue_round_total": 0,
            "current_actor_id": None,
            "current_actor_name": None,
        }
        session["round_history"] = []
        session["settlement_history"] = []
        session["issue_ledger"] = []
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["latest_purchase_plan"] = {}
        session["latest_review"] = {}
        session["latest_issue_summary"] = {}
        session["asset_manifest"] = []
        session["shared_memory"] = initial_shared_memory(budget_yuan)
        session["failed_phase"] = None
        session["last_success_phase"] = None
        session["error"] = None
        session["report_artifacts"] = None
        return session

    def _persist_session(self, session) -> None:
        self.store.save_session(_session_dataclass(session))

    def _log_execution(
        self,
        session,
        level: str,
        code: str,
        message: str,
        *,
        phase: str | None = None,
        details=None,
    ) -> None:
        append_execution_log(
            session,
            level,
            code,
            message,
            phase=phase,
            details=details,
        )

    def _apply_runtime_budget(self, session, budget_yuan: int) -> None:
        if session.get("budget_yuan") == budget_yuan:
            return
        session["budget_yuan"] = budget_yuan
        session["shared_memory"]["purchase_budget"] = f"Current purchase budget: {budget_yuan} yuan."
        self._sync_shared_blocks(session)
        self._persist_session(session)

    def _create_session(
        self,
        strategies,
        pick_size: int,
        model_name: str | None,
        budget_yuan: int,
        session_id: str | None = None,
    ):
        session = WorldSession.create(
            WORLD_V2_MARKET_RUNTIME_MODE,
            pick_size,
            budget_yuan,
            list(strategies.keys()),
            "尽量中奖，并保留可解释的社交世界决策过程。",
            model_name,
            session_id,
        ).to_dict()
        session["status"] = "idle"
        session["agents"] = []
        session["agent_state"] = {}
        session["request_metrics"] = {
            "create_agent": 0,
            "add_passage": 0,
            "update_block": 0,
            "send_message": 0,
        }
        session["progress"] = {
            "current_round": 0,
            "settled_rounds": 0,
            "awaiting_period": None,
            "dialogue_round_index": 0,
            "dialogue_round_total": 0,
            "current_actor_id": None,
            "current_actor_name": None,
        }
        session["round_history"] = []
        session["settlement_history"] = []
        session["issue_ledger"] = []
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["latest_purchase_plan"] = {}
        session["latest_review"] = {}
        session["latest_issue_summary"] = {}
        session["asset_manifest"] = []
        session["execution_log"] = []
        session["shared_memory"] = initial_shared_memory(budget_yuan)
        session["agent_block_schema_version"] = AGENT_BLOCK_SCHEMA_VERSION
        session["failed_phase"] = None
        session["last_success_phase"] = None
        session["error"] = None
        session["report_artifacts"] = None
        self._log_execution(
            session,
            "info",
            "session_created",
            "创建新的 world_v2_market 会话。",
            phase="idle",
            details=[
                f"pick_size={pick_size}",
                f"budget_yuan={budget_yuan}",
                f"strategy_count={len(strategies)}",
                f"llm_model={model_name or '-'}",
                f"runtime_backend={self._runtime_backend()}",
            ],
        )
        return session

    def _set_phase(self, session, phase: str) -> None:
        session["status"] = "running"
        session["current_phase"] = phase
        session.setdefault("progress", {})["current_actor_id"] = None
        session["progress"]["current_actor_name"] = None
        self._log_execution(
            session,
            "info",
            "phase_started",
            f"进入阶段: {phase}",
            phase=phase,
        )
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "phase_change", f"phase={phase}")])

    def _complete_phase(self, session, phase: str) -> None:
        session["last_success_phase"] = phase
        session["failed_phase"] = None
        session.setdefault("progress", {})["current_actor_id"] = None
        session["progress"]["current_actor_name"] = None
        self._log_execution(
            session,
            "info",
            "phase_completed",
            f"阶段完成: {phase}",
            phase=phase,
        )
        self._persist_session(session)

    def _set_issue_summary(self, session, **updates) -> None:
        current = dict(session.get("latest_issue_summary", {}))
        current.update({key: value for key, value in updates.items() if value is not None})
        session["latest_issue_summary"] = current
        self._persist_session(session)

    def _append_events(self, session, events: list[WorldEvent]) -> None:
        self.store.append_events(session["session_id"], events)

    def _mark_failed(self, session, assets, strategies, pick_size: int, options, exc: Exception) -> dict[str, Any]:
        failed_phase = session.get("current_phase")
        session["status"] = "failed"
        session["failed_phase"] = failed_phase
        session["current_phase"] = "failed"
        error = build_error_payload(
            exc,
            phase=str(failed_phase or "idle"),
            period=session.get("current_period"),
        )
        session["error"] = error
        self._log_execution(
            session,
            "error",
            error.get("code", "world_runtime_failed"),
            error["message"],
            phase=failed_phase,
            details=error.get("details"),
        )
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "run_failed", error["message"])])
        return self._payload(session, assets, strategies, pick_size, options)

    def _status_event(self, session, event_type: str, content: str) -> WorldEvent:
        return self._event(
            session["session_id"],
            session.get("current_period") or "-",
            session.get("current_phase") or "idle",
            event_type,
            "system",
            "World Runtime",
            content,
            metadata={"group": "system", "status": session.get("status", "-")},
        )

    def _append_public_discussion(self, session, events, persist: bool = False) -> None:
        digest = _discussion_digest(events)
        if not digest:
            return
        shared = session["shared_memory"]
        round_state = session.setdefault("current_round", {})
        issue_base = str(round_state.get("issue_base") or shared.get("current_issue", "")).strip()
        digests = list(round_state.get("discussion_digests", []))
        digests.append(digest)
        round_state["discussion_digests"] = digests[-4:]
        shared["current_issue"] = merge_issue_discussion(issue_base, round_state["discussion_digests"])
        self._sync_shared_blocks(session)
        if persist:
            self._persist_session(session)

    def _world_analyst_answer(
        self,
        session,
        prompt: str,
        assets: WorkspaceAssets | None,
    ) -> str:
        del session, prompt, assets
        raise ValueError("world_analyst has been removed from world_v2_market")

    def _client(self, session=None) -> LettaClient:
        if self.letta_client is not None:
            return self.letta_client
        reload_project_env()
        model_name = str((session or {}).get("llm_model_name") or "")
        cache_key = (
            os.environ.get("LETTA_BASE_URL", ""),
            os.environ.get("LETTA_SERVER_API_KEY", ""),
            os.environ.get("LETTA_API_KEY", ""),
            os.environ.get("LETTA_EMBEDDING_MODEL", ""),
            model_name or os.environ.get("LLM_MODEL_NAME", ""),
        )
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = LettaClient(model_name=model_name or None)
        return self._client_cache[cache_key]

    def _create_agent(self, session, name, description, memory_blocks, metadata):
        self._increment_request_metric(session, "create_agent")
        return self._client(session).create_agent(name, description, memory_blocks, metadata)

    def _add_passage(self, session, agent_id: str, text: str, tags: list[str]) -> None:
        self._increment_request_metric(session, "add_passage")
        self._client(session).add_passage(agent_id, text, tags)

    def _update_block(self, session, agent_id: str, block_label: str, value: str) -> None:
        self._increment_request_metric(session, "update_block")
        self._client(session).update_block(agent_id, block_label, value)

    def _send_message(self, session, agent_id: str, prompt: str) -> str:
        self._increment_request_metric(session, "send_message")
        client = self._client(session)
        if hasattr(client, "send_message_for_session"):
            return client.send_message_for_session(session, agent_id, prompt)
        return client.send_message(agent_id, prompt)

    def _mcp_disabled_mode(self) -> bool:
        return bool(
            getattr(self.letta_client, "local_no_mcp", False)
            or getattr(self.letta_client, "mcp_disabled", False)
        )

    def _runtime_backend(self) -> str:
        return str(getattr(self.letta_client, "runtime_backend", "")).strip() or "letta_mcp"

    def _local_no_mcp_mode(self) -> bool:
        return bool(getattr(self.letta_client, "local_no_mcp", False))

    def _increment_request_metric(self, session, name: str) -> None:
        with self._metric_lock:
            metrics = session.setdefault("request_metrics", {})
            metrics[name] = int(metrics.get(name, 0)) + 1

    def _event(
        self,
        session_id,
        period,
        phase,
        event_type,
        actor_id,
        actor_display_name,
        content,
        numbers=(),
        metadata=None,
    ) -> WorldEvent:
        return WorldEvent(
            world_id("evt"),
            session_id,
            period,
            phase,
            event_type,
            actor_id,
            actor_display_name,
            content,
            world_now(),
            tuple(numbers),
            metadata or {},
        )

    def _is_waiting_for_same_target(self, session, target_period: str) -> bool:
        latest = session.get("latest_prediction", {})
        return (
            session.get("status") == "await_result"
            and str(latest.get("period", "")).strip() == target_period
            and not session.get("error")
        )


def _pending_target_draw(assets: WorkspaceAssets):
    if not assets.pending_draws:
        raise ValueError("Persistent world requires at least one pending draw")
    return assets.pending_draws[0]


def _visible_through_period(assets: WorkspaceAssets) -> str | None:
    if not assets.completed_draws:
        return None
    return str(assets.completed_draws[-1].period).strip() or None


def _stable_hash(value: object) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _visible_history_hash(completed_draws) -> str:
    payload = [
        {
            "period": draw.period,
            "date": draw.date,
            "numbers": list(draw.numbers),
        }
        for draw in completed_draws
    ]
    return _stable_hash(payload)


def _runtime_config_hash(session, options) -> str:
    payload = {
        "runtime_mode": session.get("runtime_mode"),
        "llm_model_name": session.get("llm_model_name"),
        "pick_size": session.get("pick_size"),
        "budget_yuan": session.get("budget_yuan"),
        "selected_strategy_ids": list(session.get("selected_strategy_ids", [])),
        "agent_dialogue_enabled": bool(getattr(options, "agent_dialogue_enabled", False)),
        "agent_dialogue_rounds": int(getattr(options, "agent_dialogue_rounds", 0) or 0),
        "live_interview_enabled": bool(getattr(options, "live_interview_enabled", False)),
        "parallelism": int(getattr(options, "parallelism", 0) or 0),
        "graph_mode": str(getattr(options, "graph_mode", "")),
        "agent_block_schema_version": int(session.get("agent_block_schema_version", 0) or 0),
    }
    return _stable_hash(payload)


def _round_runtime_config(session, options) -> dict[str, Any]:
    return {
        "runtime_mode": str(session.get("runtime_mode", "")).strip(),
        "llm_model_name": str(session.get("llm_model_name") or getattr(options, "model_name", "") or "").strip(),
        "pick_size": int(session.get("pick_size", 0) or 0),
        "budget_yuan": int(session.get("budget_yuan", DEFAULT_BUDGET_YUAN) or DEFAULT_BUDGET_YUAN),
        "agent_dialogue_enabled": bool(getattr(options, "agent_dialogue_enabled", False)),
        "agent_dialogue_rounds": int(getattr(options, "agent_dialogue_rounds", 0) or 0),
        "live_interview_enabled": bool(getattr(options, "live_interview_enabled", False)),
        "parallelism": int(getattr(options, "parallelism", 0) or 0),
        "issue_parallelism": int(getattr(options, "issue_parallelism", 0) or 0),
    }


def _participant_agents_snapshot(session) -> list[dict[str, str]]:
    return [
        {
            "agent_id": str(item.get("session_agent_id", "")).strip(),
            "display_name": str(item.get("display_name", "")).strip(),
            "group": str(item.get("group", "")).strip(),
            "role_kind": str(item.get("role_kind", "")).strip(),
        }
        for item in session.get("agents", [])
    ]


def _visible_draw_history_digest(history_draws) -> str:
    rows = list(history_draws or [])
    if not rows:
        return "No visible draws."
    recent = rows[-8:]
    counter = Counter(
        int(number)
        for draw in rows[-50:]
        for number in getattr(draw, "numbers", ())
    )
    hot = ", ".join(f"{number}x{count}" for number, count in counter.most_common(8)) or "-"
    periods = ", ".join(str(draw.period) for draw in recent) or "-"
    return "\n".join(
        [
            f"- visible_draw_count={len(rows)}",
            f"- visible_through={rows[-1].period}",
            f"- recent_periods={periods}",
            f"- recent_hot_numbers={hot}",
        ]
    )


def _generator_market_board(predictions, performance: dict[str, dict[str, Any]]) -> str:
    rows = []
    for strategy_id, prediction in sorted(predictions.items()):
        item = performance.get(strategy_id, {})
        rows.append(
            f"- {prediction.display_name} ({strategy_id}): numbers={list(prediction.numbers)}, "
            f"group={prediction.group}, objective={float(item.get('objective_score', 0.0)):.3f}"
        )
    return "\n".join(rows) or NO_MARKET_BOARD


def _social_feed_memory_block(social_posts) -> str:
    rows = [_trace_event_item(item) for item in list(social_posts or [])[-8:]]
    if not rows:
        return NO_SOCIAL_FEED
    return "\n".join(
        f"- {item['display_name']} ({item['strategy_id']}): "
        f"numbers={item['numbers'] or '-'}; comment={item['comment'] or '-'}"
        for item in rows
    )


def _market_board_memory_block(
    signal_outputs,
    social_posts,
    market_ranks,
    leaderboard,
) -> str:
    sections = [
        "Generator boards:",
        _signal_output_block(signal_outputs),
        "Social feed:",
        _social_feed_memory_block(social_posts),
        "Judge boards:",
        _event_digest_block(list(market_ranks or [])),
        "Leaderboard:",
        _performance_block(_leaderboard_performance(leaderboard)),
    ]
    return "\n".join(sections)


def _purchase_board_memory_block(final_plan: dict[str, Any]) -> str:
    if not final_plan:
        return NO_PURCHASE_BOARD
    return _purchase_recommendation_block(final_plan)


def _handbook_principles_block(documents) -> str:
    docs = list(documents or ())
    for item in docs:
        name = str(getattr(item, "name", "")).strip()
        if name != HANDBOOK_PROMPT_DOC:
            continue
        compact = " ".join(str(getattr(item, "content", "")).split())
        if not compact:
            break
        payload = f"source={name}\n{compact}"
        return payload[:1800]
    return NO_HANDBOOK_PRINCIPLES


def _final_decision_constraints_block(session, target_period: str) -> str:
    visible = str(session.get("visible_through_period") or "-").strip()
    budget = int(session.get("budget_yuan", DEFAULT_BUDGET_YUAN))
    pick_size = int(session.get("pick_size", 5))
    return "\n".join(
        [
            f"- visible_through_period={visible}",
            f"- target_issue={target_period}",
            f"- official_pick_size={pick_size}",
            "- alternate_numbers_max=3",
            f"- purchase_budget_yuan={budget}",
            "- official_final_decision_owner=handbook_decider",
            "- purchase_recommendation_owner=purchase_chair",
            "- never leak actual numbers for the target issue before settlement",
            "- only use currently visible history and current shared boards",
        ]
    )


def _completed_draw_lookup(assets: WorkspaceAssets) -> dict[str, Any]:
    return {draw.period: draw for draw in assets.completed_draws}


def _period_already_settled(session, period: str) -> bool:
    return any(str(item.get("period", "")).strip() == period for item in session.get("settlement_history", []))


def _strategy_ref(strategy) -> WorldAgentRef:
    return WorldAgentRef(
        strategy.strategy_id,
        strategy.display_name,
        "strategy",
        strategy.group,
        "-",
        strategy.strategy_id,
        strategy.description,
        {"kind": strategy.kind, "uses_llm": bool(getattr(strategy, "uses_llm", False))},
    )


def _world_refs() -> list[WorldAgentRef]:
    refs = []
    for role_id, display_name, role_kind, group, description in WORLD_ROLES:
        metadata = {}
        if role_id == "purchase_chair":
            metadata = handbook_role_metadata(
                "Use the handbook as purchase doctrine, but remain executable under the current budget."
            )
        if role_id == "handbook_decider":
            metadata = handbook_role_metadata(
                "You are the only official final decider. Read every board before publishing the official prediction."
            )
        refs.append(WorldAgentRef(role_id, display_name, role_kind, group, "-", None, description, metadata))
    return refs


def _market_role_refs(session) -> list[WorldAgentRef]:
    strategy_ids = set(session.get("selected_strategy_ids", []))
    catalog = build_market_v2_catalog()
    refs = []
    for strategy in catalog.values():
        if getattr(strategy, "strategy_id", None) in strategy_ids:
            continue
        if getattr(strategy, "group", "") not in {"social", "judge"}:
            continue
        metadata = {
            "kind": getattr(strategy, "kind", "llm"),
            "uses_llm": bool(getattr(strategy, "uses_llm", False)),
        }
        metadata.update(
            handbook_role_metadata(
                "Read the handbook as discussion doctrine, but do not claim final authority."
            )
        )
        refs.append(
            WorldAgentRef(
                strategy.strategy_id,
                strategy.display_name,
                getattr(strategy, "group", "strategy"),
                getattr(strategy, "group", "-"),
                "-",
                strategy.strategy_id,
                strategy.description,
                metadata,
            )
        )
    return refs


def _purchase_refs() -> list[WorldAgentRef]:
    raise NotImplementedError("legacy purchase committee helpers are not part of world_v2_market")


def _active_agents(session, performance):
    rows = [item for item in session["agents"] if item["role_kind"] == "strategy"]
    ordered = sorted(
        rows,
        key=lambda item: (
            int(performance.get(item["session_agent_id"], {}).get("rank", 999) or 999),
            item["group"],
            item["session_agent_id"],
        ),
    )
    active = ordered
    session["active_agent_ids"] = [item["session_agent_id"] for item in active]
    return active


def _strategy_group_lookup(session) -> dict[str, str]:
    return {
        str(item["session_agent_id"]): str(item.get("group", "-"))
        for item in session.get("agents", [])
        if item.get("role_kind") == "strategy"
    }


def _grouped_generator_strategies(strategies: dict[str, object]) -> dict[str, dict[str, object]]:
    grouped = {group: {} for group in PRIMARY_GROUPS}
    for strategy_id, strategy in strategies.items():
        group = str(getattr(strategy, "group", "")).strip()
        if group not in grouped:
            continue
        grouped[group][strategy_id] = strategy
    return grouped


def _follow_up_agents(active_agents, predictions, round_index: int):
    del predictions
    if round_index <= 1:
        return active_agents
    rows = [agent for agent in active_agents if agent.get("metadata", {}).get("uses_llm", False)]
    return rows or active_agents[: min(len(active_agents), 4)]


def _agent_by_id(session, agent_id):
    for item in session["agents"]:
        if item["session_agent_id"] == agent_id:
            return item
    raise ValueError(f"Unknown world agent: {agent_id}")


def _session_agent_id(session, agent_id: str) -> str:
    target = str(agent_id).strip()
    for item in session.get("agents", []):
        if item.get("session_agent_id") == target or item.get("letta_agent_id") == target:
            return str(item.get("session_agent_id") or target)
    return target


def _agent_state_row(session, agent_id: str, display_name: str, persona: str):
    state = session.setdefault("agent_state", {})
    if agent_id not in state:
        state[agent_id] = {
            "display_name": display_name,
            "persona": persona,
            "group": "-",
            "role_kind": "strategy",
            "trust_network": [],
            "post_history": [],
            "revision_history": [],
            "recent_hits": [],
            "last_phase": "idle",
            "last_numbers": [],
            "last_comment": "",
        }
    return state[agent_id]


def _session_has_agent(session, agent_id: str) -> bool:
    return any(item["session_agent_id"] == agent_id for item in session["agents"])


def _session_compatible(session: dict[str, Any], strategies: dict[str, object]) -> bool:
    if int(session.get("agent_block_schema_version", 0) or 0) != AGENT_BLOCK_SCHEMA_VERSION:
        return False
    strategy_ids = set(strategies.keys())
    chosen = {str(item) for item in session.get("selected_strategy_ids", [])}
    if not chosen.issubset(strategy_ids):
        return False
    allowed = (
        strategy_ids
        | {ref.session_agent_id for ref in _world_refs()}
        | {ref.session_agent_id for ref in _market_role_refs(session)}
    )
    return all(str(item.get("session_agent_id", "")).strip() in allowed for item in session.get("agents", []))


def _record_agent_activity(state, period: str, phase: str, content: str, numbers) -> None:
    number_list = [int(value) for value in numbers]
    state["post_history"].append({"period": period, "phase": phase, "numbers": number_list, "comment": content})
    state["last_phase"] = phase
    state["last_numbers"] = number_list
    state["last_comment"] = content


def _interview_prompt(session, prompt: str) -> str:
    current_issue = session.get("shared_memory", {}).get("current_issue", "")
    return f"{current_issue}\n\nExternal interview question:\n{prompt}" if current_issue else prompt


def _rule_stage_interview(prediction, period: str) -> str:
    return f"{prediction.display_name} keeps {list(prediction.numbers)} for {period}. Reason: {prediction.rationale}"


def _deterministic_interview_answer(session, agent_id: str, prompt: str):
    state = session.get("agent_state", {}).get(agent_id)
    if not state:
        raise ValueError(f"Unknown world agent: {agent_id}")
    numbers = state.get("last_numbers", [])
    phase = state.get("last_phase", "opening")
    answer = (
        f"{state.get('display_name', agent_id)} currently stays with {numbers or 'the last posted numbers'} "
        f"during {phase}. Latest note: {state.get('last_comment', state.get('persona', ''))}. "
        f"Question: {prompt}"
    )
    return answer, state.get("display_name", agent_id), state.get("group", "-")


def _purchase_prompt(current_issue: str, judge: dict[str, Any], summary: str | None, budget_yuan: int) -> str:
    lines = [
        current_issue,
        "",
        f"Fixed primary numbers: {list(judge['primary_numbers'])}",
        f"Fixed alternate numbers: {list(judge['alternate_numbers'])}",
        f"Judge rationale: {judge.get('rationale', '')}",
        f"Budget: {budget_yuan} yuan",
        purchase_rule_block(),
    ]
    if summary:
        lines.extend(["Committee discussion so far:", summary])
    lines.extend(
        [
            "Return one structured purchase proposal.",
            "You may return a mixed portfolio that combines multiple structures and play sizes within budget.",
            "Do not default to single-ticket plans unless you justify why other play sizes and structures are inferior here.",
            purchase_schema(),
        ]
    )
    return "\n".join(lines)


def _purchase_json(agent_id: str, raw: str) -> dict[str, Any]:
    try:
        payload = parse_json_response(raw)
    except Exception as exc:
        raise ValueError(f"{agent_id} returned invalid purchase JSON: {raw}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{agent_id} returned non-object purchase payload: {raw}")
    return payload


def _purchase_payload(ref: WorldAgentRef, payload: dict[str, Any], prompt: str, raw: str) -> dict[str, Any]:
    plan_type = str(payload.get("plan_type", "")).strip().lower()
    if plan_type not in {"tickets", "wheel", "dan_tuo", "portfolio"}:
        raise ValueError(f"{ref.session_agent_id} returned invalid purchase proposal: {raw}")
    if plan_type != "portfolio" and "play_size" not in payload:
        raise ValueError(f"{ref.session_agent_id} returned purchase proposal without play_size: {raw}")
    play_size = int(payload.get("play_size", 0) or 0)
    return {
        "role_id": ref.session_agent_id,
        "display_name": ref.display_name,
        "plan_type": plan_type,
        "play_size": play_size,
        "plan_style": str(payload.get("plan_style", "")).strip(),
        "play_size_review": dict(payload.get("play_size_review", {})),
        "chosen_edge": str(payload.get("chosen_edge", "")).strip(),
        "trusted_strategy_ids": [str(value) for value in payload.get("trusted_strategy_ids", [])],
        "tickets": payload.get("tickets", []),
        "wheel_numbers": payload.get("wheel_numbers", []),
        "banker_numbers": payload.get("banker_numbers", []),
        "drag_numbers": payload.get("drag_numbers", []),
        "portfolio_legs": payload.get("portfolio_legs", []),
        "primary_ticket": payload.get("primary_ticket", []),
        "core_numbers": payload.get("core_numbers", []),
        "hedge_numbers": payload.get("hedge_numbers", []),
        "candidate_numbers": payload.get("candidate_numbers", []),
        "avoid_numbers": payload.get("avoid_numbers", []),
        "support_role_ids": [str(value) for value in payload.get("support_role_ids", [])],
        "comment": str(payload.get("comment", "")).strip(),
        "rationale": str(payload.get("rationale", "")).strip(),
        "prompt_preview": prompt[:500],
        "raw_response": raw[:1000],
    }


def _purchase_trace_row(round_index: int, proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": round_index,
        "role_id": proposal["role_id"],
        "display_name": proposal["display_name"],
        "plan_type": proposal["plan_type"],
        "play_size": proposal["play_size"],
        "chosen_edge": proposal["chosen_edge"],
        "plan_style": proposal["plan_style"],
        "primary_ticket": proposal["primary_ticket"],
        "wheel_numbers": proposal["wheel_numbers"],
        "banker_numbers": proposal["banker_numbers"],
        "drag_numbers": proposal["drag_numbers"],
        "support_role_ids": proposal["support_role_ids"],
        "trusted_strategy_ids": proposal["trusted_strategy_ids"],
        "comment": proposal["comment"] or proposal["rationale"],
        "rationale": proposal["rationale"],
    }


def _purchase_event(session_id: str, period: str, proposal: dict[str, Any], round_index: int) -> WorldEvent:
    return WorldEvent(
        world_id("evt"),
        session_id,
        period,
        "purchase_committee",
        "purchase_proposal",
        proposal["role_id"],
        proposal["display_name"],
        proposal["comment"] or proposal["rationale"],
        world_now(),
        tuple(_proposal_numbers(proposal)),
        {
            "group": "purchase",
            "round": round_index,
            "plan_type": proposal["plan_type"],
            "play_size": proposal["play_size"],
            "chosen_edge": proposal["chosen_edge"],
            "support_role_ids": proposal["support_role_ids"],
        },
    )


def _proposal_numbers(proposal: dict[str, Any]) -> list[int]:
    if proposal.get("plan_type") == "portfolio" and isinstance(proposal.get("portfolio_legs"), list):
        return _portfolio_numbers(proposal["portfolio_legs"])
    if proposal["primary_ticket"]:
        return [int(value) for value in proposal["primary_ticket"]]
    if proposal["wheel_numbers"]:
        return [int(value) for value in proposal["wheel_numbers"]]
    if proposal.get("candidate_numbers"):
        return [int(value) for value in proposal["candidate_numbers"]]
    numbers = [int(value) for value in proposal["banker_numbers"]]
    numbers.extend(int(value) for value in proposal["drag_numbers"] if int(value) not in numbers)
    return numbers


def _portfolio_numbers(legs: list[dict[str, Any]]) -> list[int]:
    numbers: list[int] = []
    for leg in legs:
        for value in _proposal_numbers(leg):
            if value not in numbers:
                numbers.append(value)
    return numbers


def _purchase_committee_summary(rows: Iterable[dict[str, Any]]) -> str:
    lines = []
    for item in rows:
        numbers = _proposal_numbers(item)
        lines.append(
            f"- {item['display_name']} ({item['role_id']}): type={item['plan_type']}, play_size={item['play_size']}, numbers={numbers}, "
            f"edge={item.get('chosen_edge', '-')}, support={item['support_role_ids']}, rationale={item['rationale']}"
        )
    return "\n".join(lines) or "- no proposals yet"


def _purchase_payout(tickets: tuple[tuple[int, ...], ...], actual_numbers: tuple[int, ...]) -> int | None:
    if not actual_numbers:
        return None
    actual = set(actual_numbers)
    return sum(ticket_payout(len(ticket), len(actual & set(ticket))) for ticket in tickets)


def _plan_tickets(plan: dict[str, Any]) -> tuple[tuple[int, ...], ...]:
    expanded = plan.get("expanded_tickets")
    if isinstance(expanded, list):
        return tuple(tuple(int(value) for value in ticket) for ticket in expanded if isinstance(ticket, list))
    leg = reference_leg_payload(plan)
    numbers = tuple(int(value) for value in leg.get("numbers", []))
    return (numbers,) if numbers else ()


def _discussion_digest(events: list[WorldEvent]) -> str:
    lines = []
    for event in events[-8:]:
        numbers = list(event.numbers)
        suffix = f", numbers={numbers}" if numbers else ""
        question = str(event.metadata.get("question", "")).strip() if isinstance(event.metadata, dict) else ""
        prefix = f"question={question}; " if question else ""
        lines.append(f"- [{event.phase}] {event.actor_display_name} ({event.actor_id}): {prefix}{event.content}{suffix}")
    return "\n".join(lines)


def _debate_snapshot(predictions, active_strategy_id: str) -> str:
    rows = []
    for strategy_id, prediction in predictions.items():
        label = "self" if strategy_id == active_strategy_id else "peer"
        rows.append(f"- {label} {prediction.display_name} ({strategy_id}): {list(prediction.numbers)}")
    return "\n".join(rows) or "- no strategy numbers yet"


def _recent_phase_summary(events: list[WorldEvent], phase: str) -> str:
    rows = [f"- {event.actor_display_name} ({event.actor_id}): {event.content}" for event in events[-6:] if event.phase == phase]
    return "\n".join(rows) or "- no posts yet"


def _bettor_prompt_assets(agent_row: dict[str, Any], session) -> str:
    block = registry_direct_prompt_block(agent_row, session.get("_all_documents") or ())
    return f"Bound prompt assets:\n{block}" if block else ""


def _bound_prompt_docs(ref: WorldAgentRef) -> list[str]:
    raw = (ref.metadata or {}).get("prompt_document_names")
    if not isinstance(raw, (list, tuple)):
        return []
    rows = []
    for item in raw:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _agent_prompt_passages(ref: WorldAgentRef, context) -> list[str]:
    extra = registry_prompt_passages(ref, context)
    if extra:
        return extra
    if ref.role_kind != "strategy":
        return []
    if not bool((ref.metadata or {}).get("uses_llm", False)):
        return []
    return prompt_passages(context)


def _debate_summary_text(events: list[WorldEvent], round_index: int) -> str:
    debate_posts = [event for event in events if event.event_type == "debate_post"]
    latest_posts = debate_posts[-6:]
    if not latest_posts:
        return ""
    number_counter = defaultdict(int)
    for event in latest_posts:
        for number in event.numbers:
            number_counter[int(number)] += 1
    focus = sorted(number_counter.items(), key=lambda item: (-item[1], item[0]))[:6]
    mentioned = ", ".join(f"{number}x{count}" for number, count in focus) or "-"
    agents = ", ".join(event.actor_id for event in latest_posts[-4:])
    return f"Round {round_index} summary: recent speakers={agents}; repeated numbers={mentioned}."


def _world_contributors(leaderboard: list[dict[str, Any]], predictions: dict[str, Any]) -> list[dict[str, Any]]:
    contributors = [item for item in ensemble_contributors(leaderboard) if item["strategy_id"] in predictions]
    if not contributors:
        return [
            {
                "strategy_id": strategy_id,
                "group": prediction.group,
                "group_rank": 1,
                "objective_score": 1.0,
            }
            for strategy_id, prediction in predictions.items()
        ]
    return [
        {
            **item,
            "objective_score": max(float(item.get("objective_score", 0.0)), 1.0),
        }
        for item in contributors
    ]


def _judge_rationale(
    primary: list[int],
    alternate: list[int],
    breakdown: dict[int, dict[str, object]],
    contributors: list[dict[str, Any]],
) -> str:
    top_sources = []
    for number in primary[:3]:
        item = breakdown.get(number, {})
        sources = ", ".join(item.get("sources", [])[:3]) or "-"
        top_sources.append(f"{number}<-{sources}")
    trusted = ", ".join(item["strategy_id"] for item in contributors[:5]) or "-"
    return (
        f"Deterministic ensemble synthesis selected primary={primary} and alternate={alternate}. "
        f"Top source paths: {'; '.join(top_sources) or '-'}. Trusted contributors: {trusted}."
    )


def _supplement_alternate_numbers(
    primary: list[int],
    alternate: list[int],
    predictions: dict[str, Any],
    round_state: dict[str, Any],
) -> list[int]:
    chosen = list(alternate)
    seen = set(primary) | set(chosen)
    for prediction in predictions.values():
        for number in prediction.numbers:
            normalized = int(number)
            if normalized in seen:
                continue
            chosen.append(normalized)
            seen.add(normalized)
            if len(chosen) >= 3:
                return chosen[:3]
    opening = _deserialize_prediction_map(round_state.get("opening_predictions", {}))
    for prediction in opening.values():
        for number in prediction.numbers:
            normalized = int(number)
            if normalized in seen:
                continue
            chosen.append(normalized)
            seen.add(normalized)
            if len(chosen) >= 3:
                return chosen[:3]
    return chosen[:3]


def _parallel_results(items, parallelism: int, worker):
    if parallelism <= 1 or len(items) <= 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(
        max_workers=min(parallelism, len(items)),
        thread_name_prefix="lottery-world",
    ) as pool:
        futures = [pool.submit(worker, item) for item in items]
        return [future.result() for future in futures]


def _session_dataclass(session):
    return WorldSession(
        session_id=session["session_id"],
        runtime_mode=session["runtime_mode"],
        status=session["status"],
        pick_size=session["pick_size"],
        budget_yuan=int(session.get("budget_yuan", DEFAULT_BUDGET_YUAN)),
        selected_strategy_ids=tuple(session["selected_strategy_ids"]),
        created_at=session["created_at"],
        updated_at=world_now(),
        world_goal=session["world_goal"],
        current_phase=session.get("current_phase", "idle"),
        current_period=session.get("current_period"),
        visible_through_period=session.get("visible_through_period"),
        active_agent_ids=tuple(session.get("active_agent_ids", [])),
        shared_memory=session.get("shared_memory", {}),
        agent_block_schema_version=int(session.get("agent_block_schema_version", 0) or 0),
        agents=tuple(WorldAgentRef(**item) for item in session.get("agents", [])),
        agent_state=session.get("agent_state", {}),
        request_metrics=session.get("request_metrics", {}),
        progress=session.get("progress", {}),
        round_history=tuple(session.get("round_history", [])),
        settlement_history=tuple(session.get("settlement_history", [])),
        issue_ledger=tuple(session.get("issue_ledger", [])),
        current_round=session.get("current_round", {}),
        latest_prediction=session.get("latest_prediction", {}),
        latest_purchase_plan=session.get("latest_purchase_plan", {}),
        latest_review=session.get("latest_review", {}),
        latest_issue_summary=session.get("latest_issue_summary", {}),
        asset_manifest=tuple(session.get("asset_manifest", [])),
        execution_log=tuple(session.get("execution_log", [])),
        failed_phase=session.get("failed_phase"),
        last_success_phase=session.get("last_success_phase"),
        error=session.get("error"),
        report_artifacts=session.get("report_artifacts"),
        llm_model_name=session.get("llm_model_name"),
    )


def _session_budget(session) -> int:
    return int(session.get("budget_yuan", DEFAULT_BUDGET_YUAN))


def _session_max_tickets(session) -> int:
    return max(_session_budget(session) // TICKET_COST_YUAN, 1)


def _serialize_prediction_map(predictions, leaderboard) -> dict[str, dict[str, Any]]:
    metrics_by_id = {item["strategy_id"]: item for item in leaderboard}
    return {
        strategy_id: serialize_prediction(prediction, metrics_by_id.get(strategy_id, {}), 10)
        for strategy_id, prediction in predictions.items()
    }


def _deserialize_prediction_map(payload: dict[str, Any]) -> dict[str, Any]:
    return {strategy_id: _deserialize_prediction(item) for strategy_id, item in payload.items()}


def _deserialize_prediction(payload: dict[str, Any]):
    from .models import StrategyPrediction

    ranked = tuple((int(item["number"]), float(item["score"])) for item in payload.get("ranked_scores", []))
    return StrategyPrediction(
        strategy_id=payload["strategy_id"],
        display_name=payload["display_name"],
        group=payload["group"],
        numbers=tuple(int(value) for value in payload.get("numbers", [])),
        rationale=str(payload.get("rationale", "")).strip(),
        ranked_scores=ranked,
        kind=payload.get("kind", "rule"),
        metadata=payload.get("metadata") or {},
    )


def _leaderboard_performance(leaderboard: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return build_strategy_performance(leaderboard) if leaderboard else {}


def _round_trace(round_state: dict[str, Any], debate_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phases = defaultdict(list)
    for item in round_state.get("opening_events", []):
        phases["generator_opening"].append(_trace_event_item(item))
    for item in round_state.get("interviews", []):
        phases["social_propagation"].append(_trace_event_item(item))
    for item in round_state.get("social_events", []):
        phases["social_propagation"].append(_trace_event_item(item))
    for item in round_state.get("market_ranks", []):
        phases["market_rerank"].append(_trace_event_item(item))
    for item in debate_events:
        phases["social_propagation"].append(_trace_event_item(item))
    synthesis = round_state.get("plan_synthesis", {})
    if synthesis:
        reference_leg = dict(synthesis.get("reference_leg", {}))
        phases["plan_synthesis"].append(
            {
                "strategy_id": str(synthesis.get("reference_plan_id", "purchase_chair")),
                "display_name": "Market Synthesis",
                "group": "purchase",
                "kind": "market_synthesis",
                "numbers": list(reference_leg.get("numbers", [])),
                "comment": str(synthesis.get("rationale", "")),
            }
        )
    plan = round_state.get("final_plan", {})
    if plan:
        phases["plan_synthesis"].append(
            {
                "strategy_id": "purchase_chair",
                "display_name": "LLM-Purchase-Chair",
                "group": "purchase",
                "kind": "purchase_plan",
                "numbers": reference_leg_payload(plan)["numbers"],
                "comment": str(plan.get("rationale", "")),
            }
        )
    final_decision = round_state.get("final_decision", {})
    if final_decision:
        phases["handbook_final_decision"].append(
            {
                "strategy_id": "handbook_decider",
                "display_name": "Handbook Decider",
                "group": "decision",
                "kind": "official_prediction",
                "numbers": list(final_decision.get("numbers", [])),
                "comment": str(final_decision.get("rationale", "")),
            }
        )
    return [
        {
            "stage": phase,
            "title": phase.replace("_", " ").title(),
            "active_strategy_ids": [item["strategy_id"] for item in items],
            "active_groups": sorted({item["group"] for item in items if item["group"] != "-"}),
            "items": items,
        }
        for phase, items in phases.items()
    ]


def _trace_event_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "strategy_id": item.get("actor_id", item.get("strategy_id", "-")),
            "display_name": item.get("actor_display_name", item.get("display_name", "-")),
            "group": item.get("metadata", {}).get("group", item.get("group", "-")),
            "kind": item.get("event_type", item.get("kind", "-")),
            "numbers": list(item.get("numbers", [])),
            "comment": item.get("content", item.get("comment", "")),
        }
    else:
        # Handle WorldEvent or other object types
        metadata = getattr(item, "metadata", {})
        return {
            "strategy_id": getattr(item, "actor_id", getattr(item, "strategy_id", "-")),
            "display_name": getattr(item, "actor_display_name", getattr(item, "display_name", "-")),
            "group": metadata.get("group", getattr(item, "group", "-")) if isinstance(metadata, dict) else getattr(metadata, "group", getattr(item, "group", "-")),
            "kind": getattr(item, "event_type", getattr(item, "kind", "-")),
            "numbers": list(getattr(item, "numbers", []) or []),
            "comment": getattr(item, "content", getattr(item, "comment", "")),
        }


def _purchase_recommendation_block(plan: dict[str, Any]) -> str:
    if not plan:
        return "- no purchase recommendation"
    leg = reference_leg_payload(plan)
    return "\n".join(
        [
            f"- plan_type={plan.get('plan_type', '-')}",
            f"- play_size={plan.get('play_size', '-')}",
            f"- numbers={leg.get('numbers', [])}",
            f"- cost={plan.get('total_cost_yuan', '-')}",
            f"- rationale={plan.get('rationale', '-')}",
        ]
    )


def _review_block(review: dict[str, Any]) -> str:
    if not review:
        return "- no review yet"
    return "\n".join(
        [
            f"- period={review.get('period', '-')}",
            f"- official_hits={review.get('official_hits', '-')}",
            f"- purchase_profit={review.get('purchase_profit', '-')}",
            f"- summary={review.get('summary', '-')}",
        ]
    )


def _latest_review_payload(actual_draw, final_decision, final_plan, settlement, events: list[WorldEvent]) -> dict[str, Any]:
    helpful = [event.actor_id for event in events if event.content][:3]
    summary = " | ".join(event.content for event in events[:3] if event.content) or "Postmortem captured."
    return {
        "period": actual_draw.period,
        "actual_numbers": list(actual_draw.numbers),
        "official_prediction": list(final_decision.get("numbers", [])),
        "official_hits": settlement.get("official_hits", 0),
        "purchase_plan_type": final_plan.get("plan_type"),
        "purchase_cost": settlement.get("purchase_cost_yuan", 0),
        "purchase_payout": settlement.get("purchase_payout_yuan", 0),
        "purchase_profit": settlement.get("purchase_profit", 0),
        "purchase_roi": settlement.get("purchase_roi", 0.0),
        "helpful_agents": helpful,
        "summary": summary,
    }


def _issue_ledger_entry(session, actual_draw, final_decision, final_plan, settlement, latest_review, round_state) -> dict[str, Any]:
    return {
        "visible_through_period": round_state.get("visible_through_period") or session.get("visible_through_period"),
        "predicted_period": actual_draw.period,
        "actual_numbers": list(actual_draw.numbers),
        "official_prediction": list(final_decision.get("numbers", [])),
        "official_alternate_numbers": list(final_decision.get("alternate_numbers", [])),
        "official_hits": settlement.get("official_hits", 0),
        "purchase_recommendation": {
            "plan_type": final_plan.get("plan_type"),
            "play_size": final_plan.get("play_size"),
            "numbers": reference_leg_payload(final_plan).get("numbers", []),
            "cost_yuan": settlement.get("purchase_cost_yuan", 0),
            "payout_yuan": settlement.get("purchase_payout_yuan", 0),
            "profit_yuan": settlement.get("purchase_profit", 0),
            "roi": settlement.get("purchase_roi", 0.0),
        },
        "latest_review": latest_review,
    }


def _signal_output_block(signal_outputs) -> str:
    rows = []
    for item in signal_outputs:
        payload = serialize_signal_output(item) if hasattr(item, "strategy_id") else dict(item)
        numbers = sorted(
            ((int(number), float(score)) for number, score in (payload.get("number_scores") or {}).items()),
            key=lambda value: (-value[1], value[0]),
        )[:8]
        board = ", ".join(f"{number}:{score:.2f}" for number, score in numbers) or "-"
        rows.append(
            f"- {payload.get('strategy_id', '-')}: scores={board}; "
            f"play_bias={payload.get('play_size_bias')}; structure={payload.get('structure_bias', '-')}"
        )
    return "\n".join(rows) or "- no signals"


def _performance_block(performance: dict[str, dict[str, Any]]) -> str:
    rows = []
    for strategy_id, item in sorted(performance.items(), key=lambda row: int(row[1].get("rank", 999) or 999))[:8]:
        rows.append(
            f"- #{item.get('rank', '-')} {item.get('display_name', strategy_id)} "
            f"({strategy_id}): objective={float(item.get('objective_score', 0.0)):.3f}, "
            f"roi={float(item.get('strategy_roi', 0.0)):.2f}"
        )
    return "\n".join(rows) or "- no settled performance yet"


def _event_digest_block(events: list[dict[str, Any]]) -> str:
    rows = []
    for item in events[-8:]:
        event = _trace_event_item(item)
        rows.append(
            f"- {event['display_name']} ({event['strategy_id']}): "
            f"numbers={event['numbers'] or '-'}; comment={event['comment'] or '-'}"
        )
    return "\n".join(rows) or "- no events yet"


def _bet_plan_block(bet_plans: dict[str, dict[str, Any]]) -> str:
    rows = []
    for role_id, plan in bet_plans.items():
        leg = reference_leg_payload(plan)
        rows.append(
            f"- {plan.get('display_name', role_id)} ({role_id}): "
            f"type={plan.get('plan_type', '-')}, play_size={plan.get('play_size', '-')}, "
            f"numbers={leg['numbers']}, tickets={plan.get('ticket_count', 0)}, "
            f"cost={plan.get('total_cost_yuan', 0)}, "
            f"risk={plan.get('risk_exposure', '-')}"
        )
    return "\n".join(rows) or "- no bettor plans"


def _plan_guard_lines(budget_yuan: int, max_tickets: int) -> list[str]:
    return [
        "Non-negotiable validation rules:",
        f"- Total cost must stay within {budget_yuan} yuan.",
        f"- Expanded ticket count at 1x must be <= {max_tickets}.",
        "- For portfolio, sum the expanded ticket count across all legs before you answer.",
        "- Every portfolio_legs item is live and counted toward the same budget and ticket cap.",
        "- Do not put illustrative, backup, or explanation-only legs inside portfolio_legs.",
        "- Every ticket and primary_ticket must contain exactly play_size unique numbers.",
        "- wheel_numbers, banker_numbers, and drag_numbers must not repeat numbers internally.",
        "- banker_numbers and drag_numbers must not overlap.",
    ]


def _purchase_validation_details(exc: Exception, raw: str) -> list[str]:
    return [
        f"validation_error: {str(exc).strip() or exc.__class__.__name__}",
        "portfolio_legs are all treated as executable live legs.",
        f"raw_preview: {_purchase_raw_preview(raw)}",
    ]


def _purchase_repair_prompt(prompt: str, raw: str, exc: Exception | None) -> str:
    reason = str(exc).strip() if exc else "unknown validation failure"
    return "\n".join(
        [
            prompt,
            "",
            "Validation failed for your previous purchase plan.",
            f"Failure reason: {reason}",
            "Return corrected JSON only.",
            "Do not include illustrative or alternative legs inside portfolio_legs.",
            "If you want to mention alternatives, keep them in comment or rationale only.",
            f"Previous invalid JSON:\n{_purchase_raw_preview(raw)}",
        ]
    )


def _purchase_raw_preview(raw: str) -> str:
    text = str(raw or "").strip()
    if len(text) <= PURCHASE_PLAN_RAW_PREVIEW_CHARS:
        return text
    return f"{text[:PURCHASE_PLAN_RAW_PREVIEW_CHARS]}..."


def _tool_role_matches(server_name: str, tool_name: str, role_kind: str, group: str) -> bool:
    del tool_name
    if server_name == "happy8_rules_mcp":
        return role_kind in {"judge", "purchase", "decision"}
    if server_name == "world_state_mcp":
        return group in {"social", "judge", "decision"}
    if server_name in {"kuzu_market_mcp", "report_memory_mcp"}:
        return group in {"judge", "decision"} or role_kind == "purchase"
    return False

def _process_trace(session) -> list[dict[str, Any]]:
    trace = []
    if session.get("current_round"):
        progress = session.get("progress", {})
        actor = progress.get("current_actor_name") or "-"
        trace.append(
            {
                "step": "round",
                "title": "Persistent World Round",
                "status": session.get("status", "idle"),
                "details": (
                    f"round={session['current_round'].get('round_id', '-')} / "
                    f"period={session['current_round'].get('target_period', '-')} / "
                    f"phase={session.get('current_phase', '-')} / "
                    f"actor={actor}"
                ),
            }
        )
    if session.get("settlement_history"):
        last = session["settlement_history"][-1]
        trace.append(
            {
                "step": "settlement",
                "title": "Latest Settlement",
                "status": "completed",
                "details": (
                    f"period={last.get('period', '-')} / "
                    f"official_hits={last.get('official_hits', last.get('consensus_hits', '-'))} / "
                    f"best_hits={last.get('best_hits', '-')}"
                ),
            }
        )
    return trace
