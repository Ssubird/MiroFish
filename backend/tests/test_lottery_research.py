from pathlib import Path
import tempfile

import pytest

from app import create_app
from app.config import Config
from app.services.lottery import LotteryResearchService
from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.agents.llm_agents import GraphLLMAgent, build_llm_agents
from app.services.lottery.constants import KUZU_GRAPH_MODE
from app.services.lottery.deliberation import DialogueCoordinator
from app.services.lottery.knowledge_context import KnowledgeContextBuilder
from app.services.lottery.kuzu_graph import KuzuGraphService
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, PredictionContext, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.repository import LotteryDataRepository


class DummyDialogueAgent(StrategyAgent):
    supports_dialogue = True

    def predict(self, context: PredictionContext, pick_size: int) -> StrategyPrediction:
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=(1, 2, 3, 4, 5),
            rationale="initial",
            ranked_scores=((1, 5.0),),
            kind="llm",
            metadata={},
        )

    def deliberate(self, context, own_prediction, peer_predictions, dialogue_history, pick_size, round_index):
        updated = StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=(6, 7, 8, 9, 10),
            rationale="revised",
            ranked_scores=((6, 5.0),),
            kind="llm",
            metadata={"dialogue_history": [{"round": round_index}]},
        )
        note = {
            "round": round_index,
            "strategy_id": self.strategy_id,
            "comment": "ok",
            "numbers_after": [6, 7, 8, 9, 10],
        }
        return updated, note


def _draw(period: str, numbers: tuple[int, ...]) -> DrawRecord:
    return DrawRecord(
        period=period,
        date="2026-01-01",
        chinese_date="",
        numbers=numbers,
        daily_energy=EnergySignature("乙", "酉", ("天机",)),
        hourly_energy=EnergySignature("丁", "亥", ("太阴",)),
    )


def test_lottery_overview_reads_workspace():
    service = LotteryResearchService()

    overview = service.build_overview()

    assert overview["completed_draws"] > 1800
    assert overview["pending_draws"] == 1
    assert overview["document_summary"]["total_documents"] >= 3
    assert overview["chart_summary"]["total_charts"] > 1800
    assert overview["pending_target_draw"]["period"]
    assert len(overview["available_strategies"]) >= 5
    assert overview["workspace_graph"]["node_count"] > 0
    assert "zep_graph_status" in overview
    assert "kuzu_graph_status" in overview
    assert "data" in overview["strategy_group_summary"]
    assert any(item["strategy_id"] == "chart_signature_120" for item in overview["available_strategies"])
    assert "llm_status" in overview
    if Config.LLM_API_KEY:
        llm_strategy = next(item for item in overview["available_strategies"] if item["strategy_id"] == "llm_ziwei_graph")
        assert llm_strategy["uses_llm"] is True
        assert llm_strategy["default_enabled"] is False
        judge_strategy = next(item for item in overview["available_strategies"] if item["strategy_id"] == "consensus_judge")
        assert judge_strategy["uses_llm"] is True
        assert judge_strategy["supports_dialogue"] is True


def test_lottery_backtest_produces_pending_prediction():
    strategy_ids = ["hot_50", "cold_50", "miss_120", "momentum_60", "structure_90"]
    with tempfile.TemporaryDirectory() as temp_dir:
        service = LotteryResearchService(report_writer=LotteryReportWriter(Path(temp_dir)))
        expected_pending = service.build_overview()["pending_target_draw"]["period"]
        result = service.run_backtest(
            evaluation_size=10,
            pick_size=5,
            strategy_ids=strategy_ids,
            llm_request_delay_ms=2000,
            llm_model_name="gpt-5",
            llm_retry_count=2,
            llm_retry_backoff_ms=1500,
            llm_parallelism=2,
            issue_parallelism=3,
            agent_dialogue_enabled=False,
            agent_dialogue_rounds=0,
        )

    assert len(result["leaderboard"]) >= 5
    assert result["evaluation"]["llm_request_delay_ms"] == 2000
    assert result["evaluation"]["llm_model_name"] == "gpt-5"
    assert result["evaluation"]["llm_retry_count"] == 2
    assert result["evaluation"]["llm_retry_backoff_ms"] == 1500
    assert result["evaluation"]["llm_parallelism"] == 2
    assert result["evaluation"]["issue_parallelism"] == 3
    assert result["evaluation"]["agent_dialogue_enabled"] is False
    assert result["evaluation"]["agent_dialogue_rounds"] == 0
    assert result["evaluation"]["selected_strategies"] == strategy_ids
    assert result["evaluation"]["selected_llm_strategies"] == []
    assert len(result["process_trace"]) == 5
    assert result["process_trace"][0]["step"] == "workspace"
    assert result["process_trace"][1]["step"] == "graph"
    assert result["pending_prediction"]["period"] == expected_pending
    assert len(result["pending_prediction"]["ensemble_numbers"]) == 5
    assert len(result["pending_prediction"]["coordination_trace"]) >= 1
    assert len(result["pending_prediction"]["performance_context"]) >= 1
    assert result["pending_prediction"]["purchase_plan"]["status"] in {"skipped", "ready"}
    assert result["report_artifacts"]["json_path"].endswith(".json")
    assert result["report_artifacts"]["markdown_path"].endswith(".md")
    assert result["leaderboard"][0]["latest_prediction"] is not None
    assert result["leaderboard"][0]["kind"] == "rule"
    assert result["leaderboard"][0]["group"] in {"data", "metaphysics", "hybrid"}


def test_kuzu_graph_sync_and_backtest_subset():
    repository = LotteryDataRepository()
    draws = repository.load_draws()
    subset_draws = [*draws[:75], draws[-1]]
    visible_periods = {draw.period for draw in subset_draws}
    subset_charts = [
        chart
        for chart in repository.load_chart_profiles()
        if not chart.metadata.get("period") or str(chart.metadata.get("period")) in visible_periods
    ]
    subset_docs = repository.load_knowledge_documents()

    class SubsetRepository:
        def load_draws(self):
            return subset_draws

        def load_knowledge_documents(self):
            return subset_docs

        def load_chart_profiles(self):
            return subset_charts

    with tempfile.TemporaryDirectory() as temp_dir:
        service = LotteryResearchService(
            repository=SubsetRepository(),
            kuzu_graph_service=KuzuGraphService(
                state_file=Path(temp_dir) / "kuzu_state.json",
                db_root=str(Path(temp_dir) / "kuzu_graph"),
            ),
            report_writer=LotteryReportWriter(Path(temp_dir)),
        )
        sync = service.sync_kuzu_graph(force=True)
        result = service.run_backtest(
            evaluation_size=5,
            pick_size=5,
            strategy_ids=["hot_50", "cold_50"],
            graph_mode=KUZU_GRAPH_MODE,
            issue_parallelism=2,
            agent_dialogue_enabled=False,
            agent_dialogue_rounds=0,
        )

    assert sync["available"] is True
    assert result["evaluation"]["graph_mode"] == KUZU_GRAPH_MODE
    assert len(result["leaderboard"]) == 2


def test_lottery_api_endpoint_smoke():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/lottery/overview")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    graph_response = client.get("/api/lottery/graph/status")
    assert graph_response.status_code == 200


def test_dialogue_coordinator_runs_rounds():
    coordinator = DialogueCoordinator()
    agent = DummyDialogueAgent("dummy", "Dummy", "test", 1, "hybrid")

    result = coordinator.run(
        context=PredictionContext(
            history_draws=(),
            target_draw=None,  # type: ignore[arg-type]
            knowledge_documents=(),
            chart_profiles=(),
            graph_snapshot=None,  # type: ignore[arg-type]
        ),
        strategies={"dummy": agent},
        predictions={
            "dummy": StrategyPrediction(
                strategy_id="dummy",
                display_name="Dummy",
                group="hybrid",
                numbers=(1, 2, 3, 4, 5),
                rationale="initial",
                ranked_scores=((1, 5.0),),
                kind="llm",
                metadata={},
            ),
            "rule": StrategyPrediction(
                strategy_id="rule",
                display_name="Rule",
                group="data",
                numbers=(11, 12, 13, 14, 15),
                rationale="rule",
                ranked_scores=((11, 5.0),),
                metadata={},
            ),
        },
        pick_size=5,
        rounds=1,
        parallelism=2,
    )

    assert len(result.rounds) == 1
    assert result.predictions["dummy"].numbers == (6, 7, 8, 9, 10)


def test_prompt_documents_are_excluded_but_reports_are_included_in_llm_grounding():
    draw = _draw("2026001", ())
    context = PredictionContext(
        history_draws=(),
        target_draw=draw,
        knowledge_documents=(
            KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 10, "pick 10", ("pick",)),
            KnowledgeDocument("book.md", "knowledge", "knowledge/learn/book.md", 10, "天机 太阴", ("天机", "太阴")),
            KnowledgeDocument("report.md", "report", "reports/report.md", 20, "近期冷号命中率更高", ("冷号", "命中率")),
        ),
        chart_profiles=(),
        graph_snapshot=GraphSnapshot("test", 1, 1, (), {}, (), 0, ()),
    )

    snippets = KnowledgeContextBuilder().build(context)

    assert all(item.kind != "prompt" for item in snippets)
    assert any(item.source == "book.md" for item in snippets)
    assert any(item.source == "report.md" for item in snippets)


def test_llm_prompt_enforces_single_ticket_and_reads_report():
    if not Config.LLM_API_KEY:
        pytest.skip("LLM not configured")
    agent = build_llm_agents()["llm_ziwei_graph"]
    draw = _draw("2026001", ())
    context = PredictionContext(
        history_draws=(draw,) * 60,
        target_draw=draw,
        knowledge_documents=(KnowledgeDocument("report.md", "report", "reports/report.md", 20, "冷号命中率高", ("冷号",)),),
        chart_profiles=(),
        graph_snapshot=GraphSnapshot("test", 1, 1, (), {}, (), 0, ()),
    )

    messages = agent._build_messages(context, KnowledgeContextBuilder().build(context), 5)

    assert "最终只允许输出 5 个最终下注号码" in messages[1]["content"]
    assert "不能提交候选号池或多方案" in messages[0]["content"]
    assert "外部预测/复盘报告" in messages[1]["content"]
