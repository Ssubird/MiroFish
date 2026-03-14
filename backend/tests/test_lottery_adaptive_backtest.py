from types import SimpleNamespace

import pytest

from app.services.lottery.agents.llm_agents import GraphLLMAgent
from app.services.lottery.knowledge_context import KnowledgeContextBuilder
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, PredictionContext, StrategyPrediction
from app.services.lottery.window_scoring import score_issue_window


def _draw(period: str, numbers: tuple[int, ...]) -> DrawRecord:
    return DrawRecord(
        period=period,
        date="2026-01-01",
        chinese_date="",
        numbers=numbers,
        daily_energy=EnergySignature("乙", "酉", ("天机",)),
        hourly_energy=EnergySignature("丁", "亥", ("太阴",)),
    )


def test_graph_llm_dialogue_keeps_global_context():
    agent = GraphLLMAgent("llm_test", "LLM-Test", "demo", 1, "metaphysics", prompt_mode="metaphysics")
    draw = _draw("2026001", ())
    context = PredictionContext(
        history_draws=(draw,),
        target_draw=draw,
        knowledge_documents=(KnowledgeDocument("report.md", "report", "reports/report.md", 20, "冷号命中率高", ("冷号",)),),
        chart_profiles=(),
        graph_snapshot=GraphSnapshot("test", 1, 1, ("天机",), {}, (), 0, ("a->b",)),
        strategy_performance={
            "cold_50": {
                "rank": 1,
                "display_name": "冷号-50期",
                "group": "data",
                "kind": "rule",
                "average_hits": 2.0,
                "total_hits": 2,
                "issues_scored": 1,
                "hit_stddev": 0.0,
                "recent_hits": [2],
            }
        },
    )
    prediction = StrategyPrediction("llm_test", "LLM-Test", "metaphysics", (1, 2, 3, 4, 5), "r", ((1, 5.0),), kind="llm")

    messages = agent._build_dialogue_messages(
        context,
        prediction,
        {"cold_50": {"display_name": "冷号-50期", "group": "data", "kind": "rule", "numbers": [1, 2, 3, 4, 5], "rationale": "cold"}},
        (),
        5,
        1,
        KnowledgeContextBuilder().build(context),
    )

    assert "外部预测/复盘报告" in messages[1]["content"]
    assert "图谱摘要" in messages[1]["content"]
    assert "知识片段" in messages[1]["content"]


def test_adaptive_backtest_passes_rolling_performance_to_later_issues():
    completed_draws = (
        _draw("2026001", tuple(range(1, 21))),
        _draw("2026002", tuple(range(1, 21))),
        _draw("2026003", tuple(range(21, 41))),
    )
    strategy = SimpleNamespace(display_name="Probe", group="social", kind="llm", uses_llm=True)
    calls = []

    def predictor(task, performance):
        calls.append(performance or {})
        numbers = (1, 2, 3, 4, 5) if task.index == 0 else (21, 22, 23, 24, 25)
        return {
            "probe": StrategyPrediction(
                "probe",
                "Probe",
                "social",
                numbers,
                "adaptive",
                tuple((number, 5.0 - idx) for idx, number in enumerate(numbers)),
                kind="llm",
            )
        }

    window = score_issue_window(
        completed_draws,
        2,
        {"probe": strategy},
        predictor,
        issue_parallelism=1,
        adaptive=True,
    )

    assert calls[0]["probe"]["issues_scored"] == 0
    assert calls[0]["probe"]["average_hits"] == 0.0
    assert calls[1]["probe"]["average_hits"] == 5.0
    assert calls[1]["probe"]["issues_scored"] == 1
    assert window.issue_results["probe"][0]["hits"] == 5


def test_adaptive_backtest_rejects_parallel_issue_execution():
    completed_draws = (
        _draw("2026001", tuple(range(1, 21))),
        _draw("2026002", tuple(range(1, 21))),
    )
    strategy = SimpleNamespace(display_name="Probe", group="social", kind="llm", uses_llm=True)

    with pytest.raises(ValueError, match="issue_parallelism 必须为 1"):
        score_issue_window(
            completed_draws,
            1,
            {"probe": strategy},
            lambda task, performance: {
                "probe": StrategyPrediction("probe", "Probe", "social", (1, 2, 3, 4, 5), "x", ((1, 5.0),), kind="llm")
            },
            issue_parallelism=2,
            adaptive=True,
        )
