from types import SimpleNamespace

from app.services.lottery.backtest_support import build_leaderboard
from app.services.lottery.context import attach_expert_interviews
from app.services.lottery.deliberation import DialogueCoordinator
from app.services.lottery.document_filters import grounding_documents
from app.services.lottery.models import DrawRecord, EnergySignature, KnowledgeDocument, PredictionContext, StrategyPrediction
from app.services.lottery.purchase_structures import planner_structure
from app.services.lottery.runtime_helpers import contributor_breakdown
from app.services.lottery.window_scoring import score_issue_window
from app.services.lottery.social_state import SocialStateTracker
from app.services.lottery.world_state import WorldStateTracker


def _draw(period: str, date: str) -> DrawRecord:
    return DrawRecord(
        period=period,
        date=date,
        chinese_date="",
        numbers=(),
        daily_energy=EnergySignature("甲", "子", ()),
        hourly_energy=EnergySignature("乙", "丑", ()),
    )


def test_leaderboard_uses_unified_objective_score():
    strategies = {
        "stable_hits": SimpleNamespace(
            display_name="Stable Hits",
            description="stable",
            group="data",
            required_history=50,
            kind="rule",
            uses_llm=False,
        ),
        "jackpot_roi": SimpleNamespace(
            display_name="Jackpot ROI",
            description="roi",
            group="data",
            required_history=50,
            kind="rule",
            uses_llm=False,
        ),
    }
    issue_results = {
        "stable_hits": [
            {"hits": 2, "predicted_numbers": [1, 2, 3, 4, 5]},
            {"hits": 2, "predicted_numbers": [1, 2, 3, 4, 6]},
            {"hits": 3, "predicted_numbers": [1, 2, 3, 7, 8]},
        ],
        "jackpot_roi": [
            {"hits": 1, "predicted_numbers": [9, 10, 11, 12, 13]},
            {"hits": 1, "predicted_numbers": [14, 15, 16, 17, 18]},
            {"hits": 5, "predicted_numbers": [19, 20, 21, 22, 23]},
        ],
    }

    leaderboard = build_leaderboard(strategies, issue_results, 5)

    assert leaderboard[0]["strategy_id"] == "jackpot_roi"
    assert leaderboard[0]["objective_score"] > leaderboard[1]["objective_score"]
    assert leaderboard[0]["strategy_roi"] > leaderboard[1]["strategy_roi"]


def test_grounding_documents_never_include_report_assets():
    documents = (
        KnowledgeDocument("book.md", "knowledge", "knowledge/book.md", 10, "book", ("book",)),
        KnowledgeDocument(
            "report.md",
            "report",
            "reports/report.md",
            10,
            "report",
            ("report",),
            metadata={
                "created_at": "2026-03-10T01:00:00",
                "effective_period": "2026059",
                "max_visible_period": "2026060",
            },
        ),
    )

    active_window = grounding_documents(documents, _draw("2026059", "2026-03-10"))
    last_window_issue = grounding_documents(documents, _draw("2026060", "2026-03-10"))
    historical = grounding_documents(documents, _draw("2026061", "2026-03-11"))

    assert [item.kind for item in active_window] == ["knowledge"]
    assert [item.kind for item in last_window_issue] == ["knowledge"]
    assert [item.kind for item in historical] == ["knowledge"]


def test_grounding_documents_exclude_prompt_docs_from_evidence():
    documents = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 10, "prompt", ("prompt",)),
        KnowledgeDocument("book.md", "knowledge", "knowledge/book.md", 10, "book", ("book",)),
    )

    visible = grounding_documents(documents, _draw("2026061", "2026-03-11"))

    assert [item.kind for item in visible] == ["knowledge"]


def test_expert_interviews_prioritize_top_rule_and_extract_report_evidence():
    documents = (
        KnowledgeDocument(
            "report.md",
            "report",
            "reports/report.md",
            10,
            "cold_50 在最近窗口继续领先\nmiss_120 次之",
            ("report",),
        ),
    )
    context = PredictionContext(
        history_draws=(),
        target_draw=None,  # type: ignore[arg-type]
        knowledge_documents=documents,
        chart_profiles=(),
        graph_snapshot=None,  # type: ignore[arg-type]
        strategy_performance={
            "cold_50": {"rank": 1, "objective_score": 0.4, "average_hits": 2.6, "strategy_roi": 1.3, "recent_hits": [2, 2, 3]},
            "llm_ziwei_graph": {"rank": 2, "objective_score": 0.3, "average_hits": 2.1, "strategy_roi": 0.2, "recent_hits": [2, 2, 2]},
        },
    )
    predictions = {
        "cold_50": StrategyPrediction("cold_50", "Cold", "data", (78, 42, 44, 50, 19), "冷号领先", ((78, 5.0),)),
        "llm_ziwei_graph": StrategyPrediction(
            "llm_ziwei_graph",
            "Graph",
            "metaphysics",
            (14, 25, 39, 50, 78),
            "图谱结论",
            ((14, 5.0),),
            kind="llm",
        ),
    }

    interviewed = attach_expert_interviews(context, predictions)

    assert interviewed.expert_interviews[0]["source_strategy_id"] == "cold_50"
    assert "cold_50" in interviewed.expert_interviews[0]["report_evidence"][0]


def test_window_scoring_trims_fixed_warmup_replays():
    completed = tuple(_draw(f"20260{index}", "2026-03-10") for index in range(1, 7))
    strategies = {"cold_50": SimpleNamespace(display_name="Cold", description="cold", group="data", kind="rule", required_history=1, uses_llm=False)}

    def predictor(task, performance):
        return {"cold_50": StrategyPrediction("cold_50", "Cold", "data", (1, 2, 3, 4, 5), "cold", ((1, 1.0),))}

    window = score_issue_window(completed, 2, strategies, predictor, 1, adaptive=False, warmup_size=3)

    assert len(window.issue_replays) == 2
    assert len(window.warmup_replays) == 3
    assert len(window.issue_results["cold_50"]) == 2


def test_social_state_tracker_keeps_posts_and_revisions():
    strategies = {
        "social_consensus_feed": SimpleNamespace(display_name="Consensus", social_mode="consensus"),
    }
    tracker = SocialStateTracker(strategies)
    predictions = {
        "social_consensus_feed": StrategyPrediction(
            "social_consensus_feed",
            "Consensus",
            "social",
            (1, 2, 3, 4, 5),
            "post",
            ((1, 5.0),),
            kind="llm",
            metadata={"post": "p1", "trusted_strategy_ids": ["cold_50"]},
        )
    }
    trace = [
        {
            "items": [
                {
                    "round": 1,
                    "strategy_id": "social_consensus_feed",
                    "display_name": "Consensus",
                    "group": "social",
                    "kind": "llm",
                    "comment": "revise",
                    "numbers_before": [1, 2, 3, 4, 5],
                    "numbers_after": [6, 7, 8, 9, 10],
                    "peer_strategy_ids": ["cold_50"],
                }
            ]
        }
    ]

    tracker.record_issue("2026061", predictions, trace)
    state = tracker.snapshot()["social_consensus_feed"]

    assert state["trust_network"] == ["cold_50"]
    assert len(state["post_history"]) == 1
    assert len(state["revision_history"]) == 1


def test_world_state_tracker_keeps_posts_interviews_and_trends():
    tracker = WorldStateTracker()
    predictions = {
        "cold_50": StrategyPrediction("cold_50", "Cold", "data", (78, 42, 44, 50, 19), "cold", ((78, 5.0),)),
        "social_consensus_feed": StrategyPrediction(
            "social_consensus_feed",
            "Social",
            "social",
            (78, 14, 25, 39, 50),
            "post",
            ((78, 5.0),),
            kind="llm",
            metadata={"post": "follow cold", "trusted_strategy_ids": ["cold_50"]},
        ),
    }
    tracker.record_issue(
        "2026061",
        predictions,
        [{"active_strategy_ids": ["social_consensus_feed"]}],
        (
            {
                "source_strategy_id": "cold_50",
                "display_name": "Cold",
                "numbers": [78, 42, 44, 50, 19],
                "answer": "cold wins",
                "report_evidence": ["cold_50 leads"],
            },
        ),
    )

    state = tracker.snapshot()

    assert state["issue_history"][0]["consensus_numbers"][0] == 78
    assert state["public_posts"][-1]["strategy_id"] == "social_consensus_feed"
    assert state["interview_history"][0]["source_strategy_id"] == "cold_50"


class _DialogueAgent:
    supports_dialogue = True

    def deliberate(self, context, own_prediction, peer_predictions, dialogue_history, pick_size, round_index):
        note = {
            "round": round_index,
            "strategy_id": own_prediction.strategy_id,
            "display_name": own_prediction.display_name,
            "group": own_prediction.group,
            "kind": own_prediction.kind,
            "comment": f"r{round_index}",
            "numbers_before": list(own_prediction.numbers),
            "numbers_after": list(own_prediction.numbers),
            "peer_strategy_ids": sorted(peer_predictions),
        }
        return own_prediction, note


class _LeadingAgent:
    supports_dialogue = True

    def deliberate(self, context, own_prediction, peer_predictions, dialogue_history, pick_size, round_index):
        updated = StrategyPrediction(
            own_prediction.strategy_id,
            own_prediction.display_name,
            own_prediction.group,
            (6, 7, 8, 9, 10),
            "leader updates",
            ((6, 5.0),),
            own_prediction.kind,
            own_prediction.metadata or {},
        )
        return updated, {
            "round": round_index,
            "strategy_id": own_prediction.strategy_id,
            "display_name": own_prediction.display_name,
            "group": own_prediction.group,
            "kind": own_prediction.kind,
            "comment": "leader moved first",
            "numbers_before": list(own_prediction.numbers),
            "numbers_after": list(updated.numbers),
            "peer_strategy_ids": sorted(peer_predictions),
        }


class _FollowerAgent:
    supports_dialogue = True

    def deliberate(self, context, own_prediction, peer_predictions, dialogue_history, pick_size, round_index):
        leader = peer_predictions["a_leader"]
        assert leader["numbers"] == [6, 7, 8, 9, 10]
        assert dialogue_history[-1]["strategy_id"] == "a_leader"
        updated = StrategyPrediction(
            own_prediction.strategy_id,
            own_prediction.display_name,
            own_prediction.group,
            (6, 11, 12, 13, 14),
            "follower reacts",
            ((6, 5.0),),
            own_prediction.kind,
            {"saw_peer_numbers": leader["numbers"]},
        )
        return updated, {
            "round": round_index,
            "strategy_id": own_prediction.strategy_id,
            "display_name": own_prediction.display_name,
            "group": own_prediction.group,
            "kind": own_prediction.kind,
            "comment": "follower saw live update",
            "numbers_before": list(own_prediction.numbers),
            "numbers_after": list(updated.numbers),
            "peer_strategy_ids": sorted(peer_predictions),
        }


def test_society_dialogue_uses_active_subset_and_group_mix():
    coordinator = DialogueCoordinator()
    strategies = {
        "primary_a": _DialogueAgent(),
        "primary_b": _DialogueAgent(),
        "social_a": _DialogueAgent(),
        "judge_a": _DialogueAgent(),
        "hybrid_a": _DialogueAgent(),
    }
    predictions = {
        "primary_a": StrategyPrediction("primary_a", "Primary A", "data", (1, 2, 3, 4, 5), "a", ((1, 1.0),), "llm", {}),
        "primary_b": StrategyPrediction("primary_b", "Primary B", "metaphysics", (6, 7, 8, 9, 10), "b", ((6, 1.0),), "llm", {}),
        "social_a": StrategyPrediction("social_a", "Social A", "social", (11, 12, 13, 14, 15), "c", ((11, 1.0),), "llm", {}),
        "judge_a": StrategyPrediction("judge_a", "Judge A", "judge", (16, 17, 18, 19, 20), "d", ((16, 1.0),), "llm", {}),
        "hybrid_a": StrategyPrediction("hybrid_a", "Hybrid A", "hybrid", (21, 22, 23, 24, 25), "e", ((21, 1.0),), "llm", {}),
    }
    context = PredictionContext(
        history_draws=(),
        target_draw=None,  # type: ignore[arg-type]
        knowledge_documents=(),
        chart_profiles=(),
        graph_snapshot=None,  # type: ignore[arg-type]
        strategy_performance={"social_a": {"rank": 1}, "judge_a": {"rank": 2}},
    )

    result = coordinator.run_society(context, strategies, predictions, 5, rounds=1, parallelism=3)

    assert len(result.rounds) == 1
    assert len(result.rounds[0]["active_strategy_ids"]) < len(predictions)
    assert "social" in result.rounds[0]["active_groups"]
    assert "judge" in result.rounds[0]["active_groups"]


def test_sequential_dialogue_round_reads_live_peer_updates():
    coordinator = DialogueCoordinator()
    context = PredictionContext(
        history_draws=(),
        target_draw=None,  # type: ignore[arg-type]
        knowledge_documents=(),
        chart_profiles=(),
        graph_snapshot=None,  # type: ignore[arg-type]
    )
    result = coordinator.run(
        context=context,
        strategies={"a_leader": _LeadingAgent(), "b_follower": _FollowerAgent()},
        predictions={
            "a_leader": StrategyPrediction("a_leader", "Leader", "social", (1, 2, 3, 4, 5), "a", ((1, 1.0),), "llm", {}),
            "b_follower": StrategyPrediction("b_follower", "Follower", "social", (11, 12, 13, 14, 15), "b", ((11, 1.0),), "llm", {}),
        },
        pick_size=5,
        rounds=1,
        parallelism=1,
    )

    assert result.predictions["a_leader"].numbers == (6, 7, 8, 9, 10)
    assert result.predictions["b_follower"].numbers == (6, 11, 12, 13, 14)
    assert result.rounds[0]["items"][1]["comment"] == "follower saw live update"


def test_contributor_breakdown_uses_ranked_score_confidence():
    predictions = {
        "cold_rule": StrategyPrediction(
            "cold_rule",
            "Cold Rule",
            "data",
            (1, 2, 3, 4, 5),
            "cold",
            ((1, 10.0), (2, 2.0), (3, 1.0), (4, 1.0), (5, 1.0)),
        )
    }
    contributors = [{"strategy_id": "cold_rule", "objective_score": 0.5, "group_rank": 1}]

    breakdown = contributor_breakdown(predictions, contributors)

    assert breakdown[1]["score"] > breakdown[2]["score"]
    assert breakdown[2]["score"] > breakdown[3]["score"]


def test_planner_structure_supports_wheel_and_dan_tuo():
    wheel = planner_structure({"plan_type": "wheel", "wheel_numbers": [1, 2, 3, 4, 5, 6]}, 5, 10)
    single_wheel = planner_structure({"plan_type": "wheel", "wheel_numbers": [1, 2, 3, 4, 5]}, 5, 10)
    dan_tuo = planner_structure({"plan_type": "dan_tuo", "banker_numbers": [1, 2], "drag_numbers": [3, 4, 5, 6]}, 5, 10)

    assert wheel.plan_type == "wheel"
    assert len(wheel.tickets) == 6
    assert len(single_wheel.tickets) == 1
    assert dan_tuo.plan_type == "dan_tuo"
    assert len(dan_tuo.tickets) == 4
