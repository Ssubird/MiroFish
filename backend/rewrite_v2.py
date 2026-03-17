import re
import os

filepath = r"e:\MoFish\MiroFish\backend\app\services\lottery\world_v2_runtime.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 替换 _run_prediction_cycle
new_run_cycle = """
    def _run_prediction_cycle(self, session, assets, strategies, target_draw, pick_size: int, options) -> None:
        session["status"] = "running"
        session["current_period"] = target_draw.period
        session["_all_documents"] = assets.knowledge_documents
        self._persist_session(session)
        leaderboard, performance = self._performance(strategies, session, pick_size)
        context = self._context(list(assets.completed_draws), target_draw, assets, options, performance, session)
        self._ensure_agents(session, strategies, context)
        round_state = self._load_round_state(session, target_draw)
        
        # 1. signal_opening
        signals = self._phase_signal_opening(session, round_state, context, strategies, pick_size, options.parallelism, leaderboard)
        
        # 2. social_propagation
        social_posts, interviews = self._phase_social_propagation(session, round_state, context, signals, performance, pick_size, options, leaderboard)
        
        # 3. market_rerank
        market_ranks = self._phase_market_rerank(session, round_state, context, signals, social_posts, leaderboard, options.parallelism)
        
        # 4. bettor_planning
        bet_plans = self._phase_bettor_planning(session, round_state, target_draw.period, market_ranks, options.parallelism)
        
        # 5. plan_synthesis
        synthesis = self._phase_plan_synthesis(session, round_state, target_draw.period, bet_plans)
        
        self._finalize_await_result(
            session,
            round_state,
            target_draw,
            signals,
            synthesis,
            bet_plans,
            interviews,
            social_posts,
            market_ranks,
            leaderboard,
        )

    def _phase_signal_opening(self, session, round_state, context, strategies, pick_size: int, parallelism: int, leaderboard):
        cached = _deserialize_prediction_map(round_state.get("signal_predictions", {}))
        if cached and self._can_skip_phase(session, "signal_opening"):
            return cached
        self._set_phase(session, "signal_opening")
        predictions = self._opening_predictions(context, strategies, pick_size, parallelism)
        performance = _leaderboard_performance(leaderboard)
        self._update_shared_memory(session, context, predictions, performance)
        events = self._opening_events(session, context.target_draw.period, predictions)
        self._append_events(session, events)
        round_state["signal_predictions"] = _serialize_prediction_map(predictions, leaderboard)
        round_state["signal_events"] = [item.to_dict() for item in events]
        self._set_issue_summary(
            session,
            period=context.target_draw.period,
            phase="signal_opening",
            primary_numbers=[],
            alternate_numbers=[],
            top_strategy_numbers={key: list(item.numbers) for key, item in list(predictions.items())[:6]},
        )
        self._save_round_state(session, round_state)
        self._complete_phase(session, "signal_opening")
        return predictions

    def _phase_social_propagation(self, session, round_state, context, signals, performance, pick_size: int, options, leaderboard):
        cached_posts = list(round_state.get("social_events", []))
        if cached_posts and self._can_skip_phase(session, "social_propagation"):
            return cached_posts, list(round_state.get("interviews", []))
        self._set_phase(session, "social_propagation")
        
        interviews = []
        if options.live_interview_enabled:
            interview_events = self._interviews(session, context, signals, performance, options.parallelism)
            interviews = [item.to_dict() for item in interview_events]
            self._append_events(session, interview_events)
            self._append_public_discussion(session, interview_events)
            
        # For simplicity, we reuse the debate logic for social agents, filtering for social group
        revised, social_events = self._debate(
            session,
            context,
            signals,
            performance,
            pick_size,
            options.agent_dialogue_enabled,
            options.agent_dialogue_rounds,
        )
        
        self._append_events(session, social_events)
        round_state["interviews"] = interviews
        round_state["social_events"] = [item.to_dict() for item in social_events]
        self._save_round_state(session, round_state)
        self._complete_phase(session, "social_propagation")
        return social_events, interviews

    def _phase_market_rerank(self, session, round_state, context, signals, social_posts, leaderboard, parallelism: int):
        cached = list(round_state.get("market_ranks", []))
        if cached and self._can_skip_phase(session, "market_rerank"):
            return cached
        self._set_phase(session, "market_rerank")
        # In this phase, judge agents evaluate the board
        # Here we mock a generic judge event for now, later we'll plug in the real judge agents
        judge = self._judge(session, round_state, signals, leaderboard)
        event = self._event(
            session["session_id"],
            session.get("current_period") or "-",
            "market_rerank",
            "market_judge",
            "world_runtime",
            "Market Rerank",
            judge["rationale"],
            tuple(judge["primary_numbers"]),
            {"group": "system", "alternate_numbers": judge["alternate_numbers"]},
        )
        self._append_events(session, [event])
        ranks = [event.to_dict()]
        round_state["market_ranks"] = ranks
        round_state["judge_decision"] = judge
        self._save_round_state(session, round_state)
        self._complete_phase(session, "market_rerank")
        return ranks

    def _phase_bettor_planning(self, session, round_state, period: str, market_ranks, parallelism: int):
        if "bet_plans" in round_state and self._can_skip_phase(session, "bettor_planning"):
            return round_state["bet_plans"]
        self._set_phase(session, "bettor_planning")
        
        # Here bettor personas make their plans. For now, we reuse the old purchase behavior 
        # as a mock for the bet plans until bettor agents are fully wired up.
        judge = round_state["judge_decision"]
        purchase = self._purchase(session, period, judge, (), parallelism)
        
        self._append_events(session, purchase["events"])
        bet_plans = {"default": purchase["plan"]}
        round_state["bet_plans"] = bet_plans
        round_state["purchase_events"] = [item.to_dict() for item in purchase["events"]]
        self._save_round_state(session, round_state)
        self._complete_phase(session, "bettor_planning")
        return bet_plans

    def _phase_plan_synthesis(self, session, round_state, period: str, bet_plans):
        if "plan_synthesis" in round_state and self._can_skip_phase(session, "plan_synthesis"):
            return round_state["plan_synthesis"]
        self._set_phase(session, "plan_synthesis")
        
        # Aggregate the market
        synthesis = {
            "total_market_volume_yuan": sum(plan.get("total_cost_yuan", 0) for plan in bet_plans.values()),
            "overall_sentiment": "mixed",
        }
        round_state["plan_synthesis"] = synthesis
        
        # Synthesize a final system decision for backward compatibility in latest_prediction
        judge = round_state["judge_decision"]
        self._set_issue_summary(
            session,
            period=period,
            phase="plan_synthesis",
            primary_numbers=list(judge["primary_numbers"]),
            alternate_numbers=list(judge["alternate_numbers"]),
            trusted_strategy_ids=list(judge.get("trusted_strategy_ids", [])),
            purchase_plan_type=bet_plans["default"].get("plan_type"),
            purchase_ticket_count=bet_plans["default"].get("ticket_count"),
        )
        
        self._save_round_state(session, round_state)
        self._complete_phase(session, "plan_synthesis")
        return synthesis

"""

# 用正则找出原本的 _run_prediction_cycle 到 _phase_purchase 的部分
# 注意由于它是 Python 代码，我们找 def _run_prediction_cycle 开始， 
# 一直到 def _finalize_await_result 之前

start_idx = content.find("def _run_prediction_cycle")
end_idx = content.find("def _finalize_await_result")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_run_cycle + "\n    " + content[end_idx:]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Replace successful!")
else:
    print("Could not find start or end index.")
