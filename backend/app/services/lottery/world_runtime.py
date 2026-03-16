"""Persistent Letta-backed world runtime for lottery prediction."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
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
from .constants import PRIMARY_GROUPS, WORLD_V1_RUNTIME_MODE
from .context import build_prediction_context
from .document_filters import grounding_documents, manual_reference_documents, prompt_documents
from .execution import run_strategy_stage
from .happy8_rules import DEFAULT_BUDGET_YUAN, TICKET_COST_YUAN, ticket_payout
from .letta_client import LettaClient
from .performance_summary import build_strategy_performance, performance_rows
from .purchase_structures import planner_structure
from .research_types import WorkspaceAssets
from .runtime_helpers import contributor_breakdown, serialized_predictions
from .serializers import serialize_prediction
from .world_assets import build_world_asset_manifest
from .world_analyst import ANALYST_DESCRIPTION, analyst_prompt
from .world_graph import build_world_graph
from .world_models import WorldAgentRef, WorldEvent, WorldSession, world_id, world_now
from .world_store import WorldSessionStore
from .world_support import (
    PURCHASE_ROLES,
    agent_blocks,
    comment_schema,
    debate_schema,
    ensure_alternate_numbers,
    initial_shared_memory,
    issue_block,
    merge_issue_discussion,
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
from ...config import reload_project_env


ROUND_PHASES = (
    "opening",
    "rule_interpretation",
    "public_debate",
    "judge_synthesis",
    "purchase_committee",
    "await_result",
    "settlement",
    "postmortem",
)
SHARED_BLOCKS = (
    "world_goal",
    "current_issue",
    "recent_outcomes",
    "purchase_budget",
)
WORLD_ROLES = (
    (
        "world_analyst",
        "World Analyst",
        "analyst",
        "analyst",
        ANALYST_DESCRIPTION,
    ),
    (
        "purchase_chair",
        "LLM-Purchase-Chair",
        "purchase",
        "purchase",
        "Choose the final Happy 8 purchase plan after comparing play sizes 3/4/5/6 and structures.",
    ),
)


class LotteryWorldRuntime:
    """Run the persistent `world_v1` lottery session."""

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
        if agent_id == "world_analyst":
            answer = self._world_analyst_answer(session, prompt, assets)
            display_name = "World Analyst"
            group = "analyst"
        elif _session_has_agent(session, agent_id):
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
        if pick_size != 5:
            raise ValueError("world_v1 requires pick_size=5")
        if issue_parallelism != 1:
            raise ValueError("world_v1 requires issue_parallelism=1")

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
            self._persist_session(session)
            return
        self._run_settlement_cycle(session, strategies, actual_draw, pick_size, options)

    def _run_prediction_cycle(self, session, assets, strategies, target_draw, pick_size: int, options) -> None:
        session["status"] = "running"
        session["current_period"] = target_draw.period
        self._persist_session(session)
        leaderboard, performance = self._performance(strategies, session, pick_size)
        context = self._context(list(assets.completed_draws), target_draw, assets, options, performance, session)
        self._ensure_agents(session, strategies, context)
        round_state = self._load_round_state(session, target_draw)
        opening = self._phase_opening(session, round_state, context, strategies, pick_size, options.parallelism, leaderboard)
        rule_posts = self._phase_rule_interpretation(session, round_state)
        revised, interviews, debate_events = self._phase_public_debate(
            session,
            round_state,
            context,
            opening,
            performance,
            pick_size,
            options,
            leaderboard,
        )
        judge = self._phase_judge(session, round_state, revised, leaderboard)
        purchase = self._phase_purchase(session, round_state, target_draw.period, judge, options.parallelism)
        self._finalize_await_result(
            session,
            round_state,
            target_draw,
            revised,
            judge,
            purchase["plan"],
            interviews,
            debate_events,
            rule_posts,
            leaderboard,
        )

    def _phase_opening(self, session, round_state, context, strategies, pick_size: int, parallelism: int, leaderboard):
        cached = _deserialize_prediction_map(round_state.get("opening_predictions", {}))
        if cached and self._can_skip_phase(session, "opening"):
            return cached
        self._set_phase(session, "opening")
        predictions = self._opening_predictions(context, strategies, pick_size, parallelism)
        performance = _leaderboard_performance(leaderboard)
        self._update_shared_memory(session, context, predictions, performance)
        events = self._opening_events(session, context.target_draw.period, predictions)
        self._append_events(session, events)
        round_state["opening_predictions"] = _serialize_prediction_map(predictions, leaderboard)
        round_state["opening_events"] = [item.to_dict() for item in events]
        self._set_issue_summary(
            session,
            period=context.target_draw.period,
            phase="opening",
            primary_numbers=[],
            alternate_numbers=[],
            top_strategy_numbers={key: list(item.numbers) for key, item in list(predictions.items())[:6]},
        )
        self._save_round_state(session, round_state)
        self._complete_phase(session, "opening")
        return predictions

    def _phase_rule_interpretation(self, session, round_state):
        cached = list(round_state.get("rule_posts", []))
        if cached and self._can_skip_phase(session, "rule_interpretation"):
            return cached
        self._set_phase(session, "rule_interpretation")
        digest = session["shared_memory"].get("rule_digest", "").strip() or "No deterministic rule digest yet."
        events = [
            self._event(
                session["session_id"],
                session.get("current_period") or "-",
                "rule_interpretation",
                "rule_summary",
                "world_runtime",
                "World Runtime",
                digest,
                metadata={"group": "system"},
            )
        ]
        self._append_events(session, events)
        self._append_public_discussion(session, events, persist=True)
        round_state["rule_posts"] = [item.to_dict() for item in events]
        self._set_issue_summary(
            session,
            period=session.get("current_period"),
            phase="rule_interpretation",
            primary_numbers=[],
            alternate_numbers=[],
            trusted_strategy_ids=[],
        )
        self._save_round_state(session, round_state)
        self._complete_phase(session, "rule_interpretation")
        return round_state["rule_posts"]

    def _phase_public_debate(
        self,
        session,
        round_state,
        context,
        opening,
        performance,
        pick_size: int,
        options,
        leaderboard,
    ):
        cached_predictions = _deserialize_prediction_map(round_state.get("debate_predictions", {}))
        if cached_predictions and self._can_skip_phase(session, "public_debate"):
            interviews = list(round_state.get("interviews", []))
            events = list(round_state.get("debate_events", []))
            return cached_predictions, interviews, events
        self._set_phase(session, "public_debate")
        interviews = []
        if options.live_interview_enabled:
            interview_events = self._interviews(session, context, opening, performance, options.parallelism)
            interviews = [item.to_dict() for item in interview_events]
            self._append_events(session, interview_events)
            self._append_public_discussion(session, interview_events)
        revised, debate_events = self._debate(
            session,
            context,
            opening,
            performance,
            pick_size,
            options.agent_dialogue_enabled,
            options.agent_dialogue_rounds,
        )
        self._append_events(session, debate_events)
        self._set_issue_summary(
            session,
            period=context.target_draw.period,
            phase="public_debate",
            primary_numbers=[],
            alternate_numbers=[],
            top_strategy_numbers={key: list(item.numbers) for key, item in list(revised.items())[:6]},
            active_strategy_ids=list(session.get("active_agent_ids", [])),
        )
        round_state["interviews"] = interviews
        round_state["debate_predictions"] = _serialize_prediction_map(revised, leaderboard)
        round_state["debate_events"] = [item.to_dict() for item in debate_events]
        round_state["active_agent_ids"] = list(session.get("active_agent_ids", []))
        self._save_round_state(session, round_state)
        self._complete_phase(session, "public_debate")
        return revised, interviews, round_state["debate_events"]

    def _phase_judge(self, session, round_state, predictions, leaderboard):
        cached = dict(round_state.get("judge_decision", {}))
        if cached and self._can_skip_phase(session, "judge_synthesis"):
            return cached
        self._set_phase(session, "judge_synthesis")
        judge = self._judge(session, round_state, predictions, leaderboard)
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            "judge_synthesis",
            "judge_decision",
            "world_runtime",
            "World Synthesis",
            judge["rationale"],
            tuple(judge["primary_numbers"]),
            {"group": "system", "alternate_numbers": judge["alternate_numbers"]},
        )
        self._append_events(session, [event])
        round_state["judge_decision"] = judge
        self._set_issue_summary(
            session,
            period=session.get("current_period"),
            phase="judge_synthesis",
            primary_numbers=list(judge["primary_numbers"]),
            alternate_numbers=list(judge["alternate_numbers"]),
            trusted_strategy_ids=list(judge.get("trusted_strategy_ids", [])),
        )
        self._save_round_state(session, round_state)
        self._complete_phase(session, "judge_synthesis")
        return judge

    def _phase_purchase(self, session, round_state, period: str, judge, parallelism: int):
        cached = dict(round_state.get("purchase_plan", {}))
        if cached.get("status") == "ready" and self._can_skip_phase(session, "purchase_committee"):
            return {"plan": cached, "events": list(round_state.get("purchase_events", []))}
        self._set_phase(session, "purchase_committee")
        purchase = self._purchase(session, period, judge, (), parallelism)
        self._append_events(session, purchase["events"])
        round_state["purchase_plan"] = purchase["plan"]
        round_state["purchase_events"] = [item.to_dict() for item in purchase["events"]]
        self._set_issue_summary(
            session,
            period=period,
            phase="purchase_committee",
            primary_numbers=list(judge["primary_numbers"]),
            alternate_numbers=list(judge["alternate_numbers"]),
            trusted_strategy_ids=list(judge.get("trusted_strategy_ids", [])),
            purchase_plan_type=purchase["plan"].get("plan_type"),
            purchase_play_size=purchase["plan"].get("play_size"),
            purchase_ticket_count=purchase["plan"].get("ticket_count"),
        )
        self._save_round_state(session, round_state)
        self._complete_phase(session, "purchase_committee")
        return purchase

    def _finalize_await_result(
        self,
        session,
        round_state,
        target_draw,
        predictions,
        judge,
        purchase_plan,
        interviews,
        debate_events,
        rule_posts,
        leaderboard,
    ) -> None:
        del rule_posts
        coordination = _round_trace(round_state, debate_events)
        session["status"] = "await_result"
        session["current_phase"] = "await_result"
        session["failed_phase"] = None
        session["current_period"] = target_draw.period
        session["progress"]["awaiting_period"] = target_draw.period
        round_state["status"] = "await_result"
        round_state["updated_at"] = world_now()
        session["latest_prediction"] = {
            "period": target_draw.period,
            "date": target_draw.date,
            "ensemble_numbers": list(judge["primary_numbers"]),
            "alternate_numbers": list(judge["alternate_numbers"]),
            "judge_decision": judge,
            "purchase_plan": purchase_plan,
            "strategy_predictions": serialized_predictions(predictions, leaderboard),
            "performance_context": performance_rows(_leaderboard_performance(leaderboard)),
            "coordination_trace": coordination,
            "live_interviews": interviews,
            "social_state": session.get("agent_state", {}),
            "world_state": {
                "settlement_history": session.get("settlement_history", []),
                "round_history": session.get("round_history", []),
            },
        }
        session["latest_purchase_plan"] = purchase_plan
        self._set_issue_summary(
            session,
            period=target_draw.period,
            phase="await_result",
            primary_numbers=list(judge["primary_numbers"]),
            alternate_numbers=list(judge["alternate_numbers"]),
            trusted_strategy_ids=list(judge.get("trusted_strategy_ids", [])),
            purchase_plan_type=purchase_plan.get("plan_type"),
            purchase_ticket_count=purchase_plan.get("ticket_count"),
        )
        self._save_round_state(session, round_state)
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "await_result", f"Waiting for draw result: {target_draw.period}")])

    def _run_settlement_cycle(self, session, strategies, actual_draw, pick_size: int, options) -> None:
        del strategies, pick_size
        round_state = dict(session.get("current_round", {}))
        if not round_state:
            return
        predictions = _deserialize_prediction_map(
            round_state.get("debate_predictions") or round_state.get("opening_predictions", {})
        )
        judge = dict(round_state.get("judge_decision", {}))
        purchase_plan = dict(round_state.get("purchase_plan", {}))
        if not predictions or not judge:
            return
        self._set_phase(session, "settlement")
        self._settle(session, actual_draw, predictions, judge, purchase_plan)
        self._complete_phase(session, "settlement")
        self._set_phase(session, "postmortem")
        events = self._postmortem(session, actual_draw, predictions, judge, options.parallelism)
        self._append_events(session, events)
        round_state["status"] = "settled"
        round_state["actual_numbers"] = list(actual_draw.numbers)
        round_state["postmortem_events"] = [item.to_dict() for item in events]
        round_state["updated_at"] = world_now()
        session["round_history"].append(round_state)
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["status"] = "idle"
        session["current_phase"] = "idle"
        session["current_period"] = None
        session["progress"]["awaiting_period"] = None
        session["progress"]["settled_rounds"] = int(session.get("progress", {}).get("settled_rounds", 0)) + 1
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
        self._persist_session(session)

    def _postmortem(self, session, actual_draw, predictions, judge, parallelism: int) -> list[WorldEvent]:
        summary = (
            f"Actual numbers: {list(actual_draw.numbers)}\n"
            f"Final 5: {list(judge['primary_numbers'])}\n"
            f"Alternate 3: {list(judge['alternate_numbers'])}\n"
            "Summarize what was right, what was wrong, and what to adjust next."
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
        return run_strategy_stage(context, strategies, pick_size, parallelism)

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
        self.kuzu_graph_service.sync_workspace(
            graph_docs,
            assets.chart_profiles,
            assets.completed_draws,
            assets.pending_draws,
            False,
        )
        return self.kuzu_graph_service.build_prediction_graph(
            history,
            target_draw,
            graph_docs,
            assets.chart_profiles,
        )

    def _ensure_agents(self, session, strategies, context) -> None:
        if session["agents"]:
            return
        refs = [_strategy_ref(strategy) for strategy in strategies.values()]
        refs.extend(_world_refs())
        refs.extend(_purchase_refs())
        session["agents"], session["agent_state"] = [], {}
        rows = _parallel_results(refs, min(len(refs), 6), lambda ref: self._register_agent_payload(session, ref, context))
        events = []
        for agent_row, state_row, event in rows:
            session["agents"].append(agent_row)
            session["agent_state"][agent_row["session_agent_id"]] = state_row
            events.append(event)
        self._append_events(session, events)
        self._persist_session(session)

    def _register_agent_payload(self, session, ref, context):
        bankroll = f"Budget {session['budget_yuan']} yuan. State tradeoffs and payoff target clearly." if ref.group == "purchase" else ""
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
        }
        for text in _agent_prompt_passages(ref, context):
            self._add_passage(session, letta_id, text, ["lottery", "prompt"])
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            session.get("current_phase") or "idle",
            "agent_registered",
            ref.session_agent_id,
            ref.display_name,
            f"role={ref.role_kind}, group={ref.group}",
            metadata={"group": ref.group, "role_kind": ref.role_kind},
        )
        return agent_row, state_row, event

    def _update_shared_memory(self, session, context, predictions, performance) -> None:
        shared = session["shared_memory"]
        issue_text = issue_block(context, predictions, performance)
        shared["current_issue"] = issue_text
        shared["report_digest"] = report_digest(context)
        shared["rule_digest"] = rule_digest(predictions, performance)
        shared["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        session.setdefault("current_round", {})["issue_base"] = issue_text
        self._sync_shared_blocks(session)

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
                    "opening",
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
            "public_debate",
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
            "public_debate",
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
            f"Reply publicly, cite peers if needed, then revise your five numbers if needed.\n{debate_schema(pick_size)}"
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

    def _judge(self, session, round_state, predictions, leaderboard) -> dict[str, Any]:
        contributors = _world_contributors(leaderboard, predictions)
        breakdown = contributor_breakdown(predictions, contributors)
        primary = ensemble_numbers(breakdown, session["pick_size"])
        alternate = ensure_alternate_numbers(primary, alternate_numbers(breakdown, session["pick_size"]))
        alternate = _supplement_alternate_numbers(primary, alternate, predictions, round_state)
        if len(primary) != 5 or len(alternate) != 3:
            raise ValueError(f"World synthesis produced invalid 5+3 decision: primary={primary}, alternate={alternate}")
        return {
            "primary_numbers": tuple(primary),
            "alternate_numbers": tuple(alternate),
            "trusted_strategy_ids": [item["strategy_id"] for item in contributors[:5]],
            "rationale": _judge_rationale(primary, alternate, breakdown, contributors),
            "focus": [str(number) for number in primary[:3]],
            "strategy_numbers": {strategy_id: list(prediction.numbers) for strategy_id, prediction in predictions.items()},
        }

    def _purchase(self, session, period: str, judge, actual_numbers, parallelism: int):
        budget_yuan = _session_budget(session)
        max_tickets = _session_max_tickets(session)
        events: list[WorldEvent] = []
        trace: list[dict[str, Any]] = []
        proposals: dict[str, dict[str, Any]] = {}
        for proposal in self._purchase_round(session, judge, 1, proposals, parallelism):
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
        for proposal in self._purchase_round(session, judge, 2, proposals, 1):
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
            "You must explicitly compare play sizes 3, 4, 5, and 6 before choosing one final executable structure.\n"
            "You may return a mixed portfolio that combines multiple structures and play sizes if total cost stays within budget.\n"
            "Do not default to pick-5 singles unless you clearly justify why that dominates tickets/wheel/dan_tuo in the other play sizes.\n"
            f"Return the final {budget_yuan}-yuan plan.\n{purchase_schema()}"
        )
        planner_raw = self._send_message(session, _agent_by_id(session, "purchase_chair")["letta_agent_id"], chair_prompt)
        planner = _purchase_json("purchase_chair", planner_raw)
        if planner.get("plan_type") != "portfolio" and "play_size" not in planner:
            raise ValueError(f"purchase_chair returned purchase plan without play_size: {planner_raw}")
        try:
            structure = planner_structure(planner, 5, max_tickets)
        except Exception as exc:
            raise ValueError(f"purchase_chair returned invalid purchase plan: {planner_raw}") from exc
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

    def _purchase_round(self, session, judge, round_index: int, proposals, parallelism: int):
        refs = list(_purchase_refs())
        summary = _purchase_committee_summary(proposals.values()) if proposals else None
        if round_index == 1 and parallelism > 1:
            return _parallel_results(refs, parallelism, lambda ref: self._purchase_proposal(session, judge, summary, ref))
        rows = []
        for ref in refs:
            live_summary = _purchase_committee_summary(proposals.values()) if proposals else summary
            proposal = self._purchase_proposal(session, judge, live_summary, ref)
            proposals[proposal["role_id"]] = proposal
            rows.append(proposal)
        return rows

    def _purchase_proposal(self, session, judge, summary, ref: WorldAgentRef):
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

    def _settle(self, session, actual_draw, predictions, judge, purchase_plan) -> None:
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
                "live_interview_enabled": options.live_interview_enabled,
                "budget_yuan": options.budget_yuan,
                "world_session_id": session["session_id"],
            },
            "process_trace": _process_trace(session),
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
                "current_round": session.get("current_round", {}),
                "round_history": session.get("round_history", []),
                "settlement_history": session.get("settlement_history", []),
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
            "ensemble_numbers": ensemble,
            "alternate_numbers": list(latest.get("alternate_numbers", [])),
            "ensemble_breakdown": ensemble_breakdown(ensemble, breakdown) if breakdown else [],
            "performance_context": performance_rows(performance),
            "strategy_predictions": latest.get("strategy_predictions", []),
            "coordination_trace": latest.get("coordination_trace", []),
            "judge_decision": latest.get("judge_decision", {}),
            "purchase_plan": latest.get("purchase_plan", {}),
            "live_interviews": latest.get("live_interviews", []),
            "social_state": latest.get("social_state", {}),
            "world_state": latest.get("world_state", {}),
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
        }
        session["round_history"] = []
        session["settlement_history"] = []
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["latest_purchase_plan"] = {}
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
        }
        session["round_history"] = []
        session["settlement_history"] = []
        session["current_round"] = {}
        session["latest_prediction"] = {}
        session["latest_purchase_plan"] = {}
        session["latest_issue_summary"] = {}
        session["asset_manifest"] = []
        session["shared_memory"] = initial_shared_memory(budget_yuan)
        session["failed_phase"] = None
        session["last_success_phase"] = None
        session["error"] = None
        session["report_artifacts"] = None
        return session

    def _set_phase(self, session, phase: str) -> None:
        session["status"] = "running"
        session["current_phase"] = phase
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "phase_change", f"phase={phase}")])

    def _complete_phase(self, session, phase: str) -> None:
        session["last_success_phase"] = phase
        session["failed_phase"] = None
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
        session["error"] = {
            "message": str(exc),
            "phase": failed_phase,
            "period": session.get("current_period"),
        }
        self._persist_session(session)
        self._append_events(session, [self._status_event(session, "run_failed", str(exc))])
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
        if persist:
            self._persist_session(session)

    def _world_analyst_answer(
        self,
        session,
        prompt: str,
        assets: WorkspaceAssets | None,
    ) -> str:
        if assets is None:
            raise ValueError("world_analyst requires workspace assets")
        graph = self._prediction_graph(
            list(assets.completed_draws),
            _pending_target_draw(assets),
            assets,
        )
        recent = self.get_recent_draw_stats(assets, session["session_id"])
        analyst = _agent_by_id(session, "world_analyst")
        compiled = analyst_prompt(
            session,
            prompt,
            recent,
            {
                "provider": graph.provider,
                "highlights": list(graph.highlights),
                "preview_relations": list(graph.preview_relations),
            },
        )
        return self._send_message(session, analyst["letta_agent_id"], compiled)

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
        return self._client(session).send_message(agent_id, prompt)

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
    if len(assets.pending_draws) != 1:
        raise ValueError("Persistent world requires exactly one pending draw with numbers=[]")
    return assets.pending_draws[-1]


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
    return [
        WorldAgentRef(role_id, display_name, role_kind, group, "-", None, description)
        for role_id, display_name, role_kind, group, description in WORLD_ROLES
    ]


def _purchase_refs() -> list[WorldAgentRef]:
    return [
        WorldAgentRef(role_id, display_name, "purchase", "purchase", "-", None, mandate)
        for role_id, display_name, mandate in PURCHASE_ROLES
    ]


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
    strategy_ids = set(strategies.keys())
    chosen = {str(item) for item in session.get("selected_strategy_ids", [])}
    if not chosen.issubset(strategy_ids):
        return False
    allowed = strategy_ids | {ref.session_agent_id for ref in _world_refs()} | {ref.session_agent_id for ref in _purchase_refs()}
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
            "You must explicitly compare play sizes 3, 4, 5, and 6 before choosing one.",
            "You may return a mixed portfolio that combines multiple structures and play sizes within budget.",
            "Do not default to pick-5 singles unless you justify why other play sizes and structures are inferior here.",
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


def _agent_prompt_passages(ref: WorldAgentRef, context) -> list[str]:
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
        active_agent_ids=tuple(session.get("active_agent_ids", [])),
        shared_memory=session.get("shared_memory", {}),
        agents=tuple(WorldAgentRef(**item) for item in session.get("agents", [])),
        agent_state=session.get("agent_state", {}),
        request_metrics=session.get("request_metrics", {}),
        progress=session.get("progress", {}),
        round_history=tuple(session.get("round_history", [])),
        settlement_history=tuple(session.get("settlement_history", [])),
        current_round=session.get("current_round", {}),
        latest_prediction=session.get("latest_prediction", {}),
        latest_purchase_plan=session.get("latest_purchase_plan", {}),
        latest_issue_summary=session.get("latest_issue_summary", {}),
        asset_manifest=tuple(session.get("asset_manifest", [])),
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
        phases["opening"].append(_trace_event_item(item))
    for item in round_state.get("rule_posts", []):
        phases["rule_interpretation"].append(_trace_event_item(item))
    for item in round_state.get("interviews", []):
        phases["public_debate"].append(_trace_event_item(item))
    for item in debate_events:
        phases["public_debate"].append(_trace_event_item(item))
    judge = round_state.get("judge_decision", {})
    if judge:
        phases["judge_synthesis"].append(
            {
                "strategy_id": "world_runtime",
                "display_name": "World Synthesis",
                "group": "system",
                "kind": "judge_decision",
                "numbers": list(judge.get("primary_numbers", [])),
                "comment": judge.get("rationale", ""),
            }
        )
    plan = round_state.get("purchase_plan", {})
    if plan:
        phases["purchase_committee"].append(
            {
                "strategy_id": "purchase_chair",
                "display_name": "LLM-Purchase-Chair",
                "group": "purchase",
                "kind": "purchase_plan",
                "numbers": list(plan.get("primary_prediction", [])),
                "comment": (plan.get("planner") or {}).get("rationale", ""),
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


def _trace_event_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": item.get("actor_id", item.get("strategy_id", "-")),
        "display_name": item.get("actor_display_name", item.get("display_name", "-")),
        "group": item.get("metadata", {}).get("group", item.get("group", "-")),
        "kind": item.get("event_type", item.get("kind", "-")),
        "numbers": list(item.get("numbers", [])),
        "comment": item.get("content", item.get("comment", "")),
    }


def _process_trace(session) -> list[dict[str, Any]]:
    trace = []
    if session.get("current_round"):
        trace.append(
            {
                "step": "round",
                "title": "Persistent World Round",
                "status": session.get("status", "idle"),
                "details": (
                    f"round={session['current_round'].get('round_id', '-')} / "
                    f"period={session['current_round'].get('target_period', '-')} / "
                    f"phase={session.get('current_phase', '-')}"
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
                    f"consensus_hits={last.get('consensus_hits', '-')} / "
                    f"best_hits={last.get('best_hits', '-')}"
                ),
            }
        )
    return trace
