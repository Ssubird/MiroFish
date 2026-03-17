import re

filepath = r"e:\MoFish\MiroFish\backend\app\services\lottery\world_v2_runtime.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

part2 = """
    def _finalize_await_result(
        self,
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
    ) -> None:
        coordination = _round_trace(round_state, social_posts)
        session["status"] = "await_result"
        session["current_phase"] = "await_result"
        session["failed_phase"] = None
        session["current_period"] = target_draw.period
        session["progress"]["awaiting_period"] = target_draw.period
        round_state["status"] = "await_result"
        round_state["updated_at"] = world_now()
        
        judge = round_state.get("judge_decision", {})
        session["latest_prediction"] = {
            "period": target_draw.period,
            "date": target_draw.date,
            "ensemble_numbers": list(judge.get("primary_numbers", [])),
            "alternate_numbers": list(judge.get("alternate_numbers", [])),
            "judge_decision": judge,
            "purchase_plan": bet_plans.get("default", {}),
            "strategy_predictions": serialized_predictions(signals, leaderboard),
            "performance_context": performance_rows(_leaderboard_performance(leaderboard)),
            "coordination_trace": coordination,
            "live_interviews": interviews,
            "social_state": session.get("agent_state", {}),
            "world_state": {
                "settlement_history": session.get("settlement_history", []),
                "round_history": session.get("round_history", []),
            },
        }
        session["latest_purchase_plan"] = bet_plans.get("default", {})
        
        # update summary again to be sure
        self._set_issue_summary(
            session,
            period=target_draw.period,
            phase="await_result",
            primary_numbers=list(judge.get("primary_numbers", [])),
            alternate_numbers=list(judge.get("alternate_numbers", [])),
            trusted_strategy_ids=list(judge.get("trusted_strategy_ids", [])),
        )
        self._save_round_state(session, round_state)
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
        judge = dict(round_state.get("judge_decision", {}))
        bet_plans = dict(round_state.get("bet_plans", {}))
        
        if not signals or not judge:
            return
            
        self._set_phase(session, "settlement")
        self._settle(session, actual_draw, signals, judge, bet_plans)
        self._complete_phase(session, "settlement")
        
        self._set_phase(session, "postmortem")
        events = self._postmortem(session, actual_draw, signals, judge, options.parallelism)
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

    def _settle(self, session, actual_draw, signals, judge, bet_plans) -> None:
        actual = set(actual_draw.numbers)
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
        
        # Calculate market payout from bet_plans
        market_total_cost = 0
        market_total_payout = 0
        for plan_name, plan in bet_plans.items():
            market_total_cost += plan.get("total_cost_yuan", 0)
            market_total_payout += plan.get("total_payout", 0)
            
        session["settlement_history"].append(
            {
                "period": actual_draw.period,
                "consensus_numbers": list(judge.get("primary_numbers", [])),
                "alternate_numbers": list(judge.get("alternate_numbers", [])),
                "actual_numbers": list(actual_draw.numbers),
                "consensus_hits": len(actual & set(judge.get("primary_numbers", []))),
                "best_hits": best_hits,
                "best_strategy_ids": [sid for sid, value in hits.items() if value == best_hits][:3],
                "purchase_profit": market_total_payout - market_total_cost,
                "strategy_issue_results": strategy_issue_results,
            }
        )
        session["shared_memory"]["recent_outcomes"] = recent_outcomes_text(list(session.get("settlement_history", [])))
        self._sync_shared_blocks(session)
        self._persist_session(session)

"""

start_idx = content.find("def _finalize_await_result(")
end_idx = content.find("def _postmortem(")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + part2 + "\n    " + content[end_idx:]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Replace Part 2 successful!")
else:
    print("Could not find start or end index.")
