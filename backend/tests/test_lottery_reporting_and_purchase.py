from types import SimpleNamespace

import pytest

from app.services.lottery.agents.prompt_blocks import single_ticket_rule
from app.services.lottery.models import KnowledgeDocument, PredictionContext, StrategyPrediction
from app.services.lottery.purchase_discussion import PURCHASE_ROLES, PurchaseDiscussionService
from app.services.lottery.purchase_helpers import clean_numbers
from app.services.lottery.purchase_plan import PurchasePlanRequest, PurchasePlanService
from app.services.lottery.purchase_structures import planner_structure
from app.services.lottery.report_markdown import build_markdown_report
from app.services.lottery.research_types import WindowBacktest
from app.services.lottery.world_support import purchase_rule_block, purchase_schema


class DummyDiscussionService:
    def build(self, request, fallback_trusted_ids):
        return {
            "planner": {
                "role_id": "purchase_chair",
                "display_name": "LLM-Purchase-Chair",
                "kind": "llm",
                "model": "gpt-5.4",
                "plan_style": "balanced",
                "plan_type": "wheel",
                "trusted_strategy_ids": list(fallback_trusted_ids),
                "primary_ticket": [78, 42, 7, 44, 5],
                "core_numbers": [78, 42, 7],
                "hedge_numbers": [44, 5, 19],
                "avoid_numbers": [12],
                "tickets": [],
                "wheel_numbers": [78, 42, 7, 44, 5, 19],
                "banker_numbers": [],
                "drag_numbers": [],
                "rationale": "Use the fixed primary ticket and one extra hedge number for structured coverage.",
                "focus": ["cold", "coverage"],
                "comment": "",
                "support_role_ids": ["coverage_builder"],
                "system_prompt": "system",
                "user_prompt_preview": "user",
            },
            "discussion_agents": [
                {
                    "role_id": "budget_guard",
                    "display_name": "LLM-Budget-Guard",
                    "plan_type": "tickets",
                    "plan_style": "tight",
                    "trusted_strategy_ids": ["cold_50"],
                    "primary_ticket": [78, 42, 7, 44, 5],
                    "rationale": "Stay concentrated.",
                    "user_prompt_preview": "budget",
                },
                {
                    "role_id": "coverage_builder",
                    "display_name": "LLM-Coverage-Builder",
                    "plan_type": "wheel",
                    "plan_style": "balanced",
                    "trusted_strategy_ids": ["cold_50"],
                    "wheel_numbers": [78, 42, 7, 44, 5, 19],
                    "rationale": "Expand with one hedge number.",
                    "user_prompt_preview": "coverage",
                },
            ],
            "discussion_trace": [
                {
                    "round": 1,
                    "role_id": "coverage_builder",
                    "display_name": "LLM-Coverage-Builder",
                    "comment": "I support adding one hedge number instead of many scattered tickets.",
                    "support_role_ids": ["budget_guard"],
                    "plan_type": "wheel",
                    "primary_ticket": [],
                    "wheel_numbers": [78, 42, 7, 44, 5, 19],
                    "banker_numbers": [],
                    "drag_numbers": [],
                }
            ],
        }


def test_clean_numbers_accepts_single_nested_ticket_and_rejects_multi_ticket():
    assert clean_numbers([[1, 2, 3, 4, 5]], 5) == [1, 2, 3, 4, 5]
    with pytest.raises(ValueError):
        clean_numbers([[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]], 5)


def test_single_ticket_rule_reserves_expansion_for_purchase_committee():
    rule = single_ticket_rule(5)

    assert "Output exactly 5 numbers" in rule
    assert "1-80" in rule


def test_purchase_prompt_guidance_forces_play_size_comparison():
    rule_block = purchase_rule_block()
    schema = purchase_schema()

    assert "Compare all available play sizes" in rule_block
    assert "Do not place illustrative, backup, or reference-only legs inside portfolio_legs." in rule_block
    assert "Multiplier: 1-15x" in rule_block
    assert '"play_size_review"' in schema
    assert '"chosen_edge"' in schema
    assert '"portfolio_legs"' in schema
    assert "do not put illustrative or reference-only alternatives into portfolio_legs" in schema


def test_purchase_discussion_messages_include_budget_primary_and_alternates():
    service = PurchaseDiscussionService(budget_yuan=50, ticket_cost_yuan=2, max_tickets=25)
    request = SimpleNamespace(
        context=PredictionContext(
            history_draws=(),
            target_draw=SimpleNamespace(period="2026063", date="2026-03-15"),
            knowledge_documents=(
                KnowledgeDocument(
                    "prompt.md",
                    "prompt",
                    "knowledge/prompts/prompt.md",
                    10,
                    "Focus on cold numbers when evidence is stable.",
                    ("cold",),
                ),
            ),
            chart_profiles=(),
            graph_snapshot=None,  # type: ignore[arg-type]
            strategy_performance={
                "cold_50": {
                    "rank": 1,
                    "display_name": "Cold 50",
                    "average_hits": 2.6,
                    "objective_score": 0.4,
                    "strategy_roi": 1.3,
                    "hit_stddev": 0.8,
                    "recent_hits": [2, 2, 3],
                }
            },
            expert_interviews=(
                {
                    "source_strategy_id": "cold_50",
                    "display_name": "Cold 50",
                    "group": "data",
                    "kind": "rule",
                    "rank": 1,
                    "objective_score": 0.4,
                    "average_hits": 2.6,
                    "strategy_roi": 1.3,
                    "recent_hits": [2, 2, 3],
                    "numbers": [78, 42, 44, 50, 19],
                    "answer": "Cold numbers are still leading.",
                    "report_evidence": ["prediction_report.md: cold numbers stayed ahead."],
                },
            ),
            world_state={"trend_numbers": [{"number": 78, "mentions": 3}]},
            social_state={"social_consensus_feed": {"display_name": "Consensus", "trust_network": ["cold_50"], "post_history": []}},
        ),
        pending_predictions={
            "cold_50": StrategyPrediction("cold_50", "Cold 50", "data", (78, 42, 44, 50, 19), "cold", ((78, 5.0),), "llm")
        },
        performance={
            "cold_50": {
                "rank": 1,
                "display_name": "Cold 50",
                "average_hits": 2.6,
                "objective_score": 0.4,
                "strategy_roi": 1.3,
                "hit_stddev": 0.8,
                "recent_hits": [2, 2, 3],
            }
        },
        coordination_trace=(),
        ensemble_numbers=(78, 42, 7, 44, 5),
        alternate_numbers=(19, 23, 61),
    )

    messages = service._proposal_messages(PURCHASE_ROLES[0], request)
    prompt = messages[1]["content"]

    assert "Budget: 50 yuan" in prompt
    assert "Reference Ticket (5 numbers): [78, 42, 7, 44, 5]" in prompt
    assert "Hedge Pool: [19, 23, 61]" in prompt
    assert "External Reports:" in prompt
    assert "Persistent Social State:" in prompt


def test_purchase_plan_returns_discussion_payload_when_ready(monkeypatch):
    monkeypatch.setattr("app.services.lottery.purchase_plan.Config.LLM_API_KEY", "test-key")
    service = PurchasePlanService(discussion_service=DummyDiscussionService())
    request = PurchasePlanRequest(
        context=PredictionContext(
            history_draws=(),
            target_draw=SimpleNamespace(period="2026063", date="2026-03-15"),
            knowledge_documents=(),
            chart_profiles=(),
            graph_snapshot=None,  # type: ignore[arg-type]
        ),
        pending_predictions={
            "cold_50": StrategyPrediction("cold_50", "Cold 50", "data", (78, 42, 7, 44, 5), "cold", ((78, 5.0),), "llm")
        },
        strategies={},
        performance={"cold_50": {"rank": 1, "display_name": "Cold 50", "average_hits": 2.4, "objective_score": 0.3, "strategy_roi": 0.4}},
        window_backtest=WindowBacktest({}, ()),
        pick_size=5,
        ensemble_numbers=(78, 42, 7, 44, 5),
        coordination_trace=(),
        alternate_numbers=(19, 23, 61),
    )

    plan = service.build(request)

    assert plan["status"] == "ready"
    assert plan["budget_yuan"] == 50
    assert plan["primary_prediction"] == [78, 42, 7, 44, 5]
    assert plan["alternate_numbers"] == [19, 23, 61]
    assert plan["discussion_agents"][0]["role_id"] == "budget_guard"
    assert plan["discussion_trace"][0]["role_id"] == "coverage_builder"
    assert plan["plan_type"] == "wheel"


def test_planner_structure_supports_pick6_wheel_under_budget():
    structure = planner_structure(
        {
            "plan_type": "wheel",
            "play_size": 6,
            "wheel_numbers": [11, 12, 13, 14, 15, 16],
        },
        5,
        10,
    )

    assert structure.plan_type == "wheel"
    assert structure.play_size == 6
    assert len(structure.tickets) == 1
    assert structure.summary["play_label"] == "选6"


def test_planner_structure_supports_multi_leg_portfolio_under_budget():
    structure = planner_structure(
        {
            "plan_type": "portfolio",
            "portfolio_legs": [
                {
                    "plan_type": "tickets",
                    "play_size": 5,
                    "tickets": [[11, 12, 13, 14, 15], [11, 12, 13, 14, 16]],
                },
                {
                    "plan_type": "dan_tuo",
                    "play_size": 4,
                    "banker_numbers": [21, 22],
                    "drag_numbers": [23, 24, 25],
                },
            ],
        },
        5,
        10,
    )

    assert structure.plan_type == "portfolio"
    assert len(structure.tickets) == 5
    assert len(structure.summary["portfolio_legs"]) == 2
    assert structure.summary["portfolio_legs"][1]["play_label"] == "选4"


def test_markdown_report_contains_purchase_committee_and_discussion():
    payload = {
        "report_artifacts": {
            "run_id": "demo",
            "saved_at": "2026-03-15T00:00:00",
            "json_path": "a.json",
            "markdown_path": "a.md",
        },
        "dataset": {
            "completed_draws": 10,
            "pending_draws": 1,
            "latest_completed_period": "2026062",
            "pending_target_period": "2026063",
        },
        "evaluation": {
            "evaluation_size": 5,
            "warmup_size": 3,
            "pick_size": 5,
            "graph_mode": "kuzu",
            "llm_model_name": "gpt-5.4",
            "llm_parallelism": 2,
            "issue_parallelism": 1,
            "agent_dialogue_enabled": True,
            "agent_dialogue_rounds": 2,
            "objective_policy": {"sort_key": "objective_score", "weights": {}},
        },
        "process_trace": [{"title": "Load Workspace", "status": "completed", "details": "ok"}],
        "leaderboard": [],
        "pending_prediction": {
            "period": "2026063",
            "date": "2026-03-15",
            "ensemble_numbers": [78, 42, 7, 44, 5],
            "alternate_numbers": [19, 23, 61],
            "ensemble_breakdown": [{"number": 78, "score": 3.0, "sources": ["Cold 50"]}],
            "signal_outputs": [
                {
                    "strategy_id": "cold_50",
                    "regime_label": "cold",
                    "play_size_bias": 5,
                    "structure_bias": "wheel",
                    "number_scores": {"78": 5.0, "42": 4.5, "19": 3.2},
                    "evidence_refs": ["prediction_report.md:1"],
                    "public_post": "Cold numbers still lead.",
                }
            ],
            "performance_context": [],
            "strategy_predictions": [],
            "coordination_trace": [],
            "social_state": {},
            "world_state": {},
            "bet_plans": {
                "steady_bettor": {
                    "display_name": "Steady Bettor",
                    "plan_type": "wheel",
                    "play_size": 5,
                    "total_cost_yuan": 12,
                    "risk_exposure": "balanced",
                    "trusted_strategy_ids": ["cold_50"],
                    "rationale": "Keep one core ticket with a light hedge.",
                    "plan_structure": {
                        "primary_ticket": [78, 42, 7, 44, 5],
                        "wheel_numbers": [78, 42, 7, 44, 5, 19],
                        "combination_count": 6,
                    },
                    "legs": [
                        {
                            "plan_type": "wheel",
                            "play_size": 5,
                            "numbers": [78, 42, 7, 44, 5],
                        }
                    ],
                }
            },
            "market_synthesis": {
                "reference_plan_id": "purchase_chair",
                "reference_leg": {
                    "plan_type": "wheel",
                    "play_size": 5,
                    "numbers": [78, 42, 7, 44, 5],
                },
                "hedge_pool": [19, 23, 61],
                "consensus_number_scores": [{"number": 78, "score": 9.5}, {"number": 42, "score": 8.7}],
                "total_market_volume_yuan": 12,
                "active_bettor_count": 1,
                "trusted_strategy_ids": ["cold_50"],
                "rationale": "Adopt the market reference ticket and keep a compact hedge pool.",
            },
            "judge_decision": {
                "primary_numbers": [78, 42, 7, 44, 5],
                "alternate_numbers": [19, 23, 61],
                "trusted_strategy_ids": ["cold_50"],
                "rationale": "Compatibility projection from market synthesis.",
            },
            "purchase_plan": {
                "status": "ready",
                "game": "Happy 8",
                "budget_yuan": 50,
                "ticket_count": 6,
                "primary_prediction": [78, 42, 7, 44, 5],
                "alternate_numbers": [19, 23, 61],
                "plan_type": "wheel",
                "planner": {
                    "display_name": "LLM-Purchase-Chair",
                    "model": "gpt-5.4",
                    "plan_style": "balanced",
                    "trusted_strategy_ids": ["cold_50"],
                    "core_numbers": [78, 42],
                    "hedge_numbers": [19],
                    "avoid_numbers": [12],
                    "rationale": "Use one extra hedge number.",
                    "user_prompt_preview": "planner prompt",
                },
                "discussion_agents": [
                    {
                        "role_id": "coverage_builder",
                        "display_name": "LLM-Coverage-Builder",
                        "plan_type": "wheel",
                        "plan_style": "balanced",
                        "trusted_strategy_ids": ["cold_50"],
                        "wheel_numbers": [78, 42, 7, 44, 5, 19],
                        "rationale": "Expand with one hedge number.",
                        "user_prompt_preview": "committee prompt",
                    }
                ],
                "discussion_trace": [
                    {
                        "round": 1,
                        "role_id": "coverage_builder",
                        "display_name": "LLM-Coverage-Builder",
                        "comment": "Expand carefully around the primary ticket.",
                        "support_role_ids": ["budget_guard"],
                        "plan_type": "wheel",
                        "primary_ticket": [],
                        "wheel_numbers": [78, 42, 7, 44, 5, 19],
                        "banker_numbers": [],
                        "drag_numbers": [],
                    }
                ],
                "plan_structure": {
                    "primary_ticket": [78, 42, 7, 44, 5],
                    "wheel_numbers": [78, 42, 7, 44, 5, 19],
                    "combination_count": 6,
                },
                "trusted_strategies": [],
                "tickets": [{"index": 1, "numbers": [78, 42, 7, 44, 5]}],
                "historical_backtest": {
                    "total_cost": 50,
                    "total_payout": 60,
                    "net_profit": 10,
                    "roi": 0.2,
                    "winning_issues": 1,
                    "recent_issue_profit": [],
                },
            },
        },
    }

    report = build_markdown_report(payload)

    assert "Reference Ticket" in report
    assert "Hedge Pool" in report
    assert "### Signal Outputs" in report
    assert "### Market Bet Plans" in report
    assert "### Market Synthesis" in report
    assert "### Judge Projection (Compatibility)" in report
    assert "### Purchase Plan" in report
    assert "#### Purchase Committee" in report
    assert "#### Purchase Discussion" in report
    assert "Primary Prediction" not in report
    assert "Alternate 3 Numbers" not in report
    assert "Planner Prompt Preview" in report
