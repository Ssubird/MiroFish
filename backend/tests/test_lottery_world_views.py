from pathlib import Path
import tempfile

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.research_types import WorkspaceAssets
from app.services.lottery.world_runtime import LotteryWorldRuntime
from app.services.lottery.world_store import WorldSessionStore


class FakeGraphService:
    def build_prediction_graph(self, history, target_draw, documents, charts):
        return GraphSnapshot(
            "prediction",
            3,
            2,
            ("冷号", "命盘"),
            {"冷号": 2.0, "命盘": 1.5},
            tuple(item.name for item in documents),
            len(charts),
            ("document->concept", "draw->concept"),
            provider="kuzu",
            backend_graph_id="kuzu_local",
        )

    def build_workspace_graph(self, documents, charts, completed_draws, pending_draw):
        return GraphSnapshot(
            "workspace",
            3,
            2,
            ("workspace",),
            {"workspace": 1.0},
            tuple(item.name for item in documents),
            len(charts),
            ("workspace->prompt",),
        )


class FakeLettaClient:
    def __init__(self):
        self.blocks = {}

    def create_agent(self, name, description, memory_blocks, metadata=None):
        agent_id = f"letta_{name}"
        self.blocks[agent_id] = dict(memory_blocks)
        return agent_id

    def update_block(self, agent_id, block_label, value):
        self.blocks.setdefault(agent_id, {})[block_label] = value

    def add_passage(self, agent_id, text, tags=None):
        return None

    def send_message(self, agent_id, content):
        if "Answer as the world analyst" in content:
            return "World Analyst: current disagreement is low and the strongest cluster is 1/2/3/4/5."
        if "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"portfolio","play_size":4,'
                '"play_size_review":{"3":"low edge","4":"best","5":"too concentrated","6":"too loose"},'
                '"chosen_edge":"split coverage","portfolio_legs":[{"plan_type":"tickets","play_size":4,"tickets":[[1,2,3,4]],'
                '"primary_ticket":[1,2,3,4],"comment":"base leg","rationale":"base leg"}],'
                '"primary_ticket":[1,2,3,4],"core_numbers":[1,2,3],"hedge_numbers":[4,5],'
                '"avoid_numbers":[10],"trusted_strategy_ids":["cold_rule"],"comment":"chair closes","rationale":"chair closes"}'
            )
        if "budget_guard" in agent_id or "coverage_builder" in agent_id or "upside_hunter" in agent_id:
            return (
                '{"plan_style":"committee","plan_type":"tickets","play_size":4,'
                '"play_size_review":{"3":"thin","4":"best","5":"too tight","6":"too diffuse"},'
                '"chosen_edge":"cover core four","tickets":[[1,2,3,4]],"primary_ticket":[1,2,3,4],'
                '"core_numbers":[1,2,3],"hedge_numbers":[4,5],"avoid_numbers":[10],"support_role_ids":[],'
                '"comment":"keep four-core","rationale":"keep four-core"}'
            )
        return '{"numbers":[1,2,3,4,5],"comment":"stay with cold cluster","support_agent_ids":["cold_rule"],"rationale":"cold remains"}'


class RuleAgent(StrategyAgent):
    def __init__(self, strategy_id, display_name, numbers):
        super().__init__(strategy_id, display_name, f"{display_name} description", 1, "data")
        self._numbers = numbers

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=self._numbers,
            rationale=f"{self.display_name} picks cold trend",
            ranked_scores=tuple((number, 10.0 - index) for index, number in enumerate(self._numbers)),
            kind="rule",
            metadata={},
        )


class WorkspaceRepository:
    def __init__(self, workspace):
        self.workspace = workspace

    def load_draws(self):
        return [*self.workspace.completed_draws, *self.workspace.pending_draws]

    def load_knowledge_documents(self):
        return list(self.workspace.knowledge_documents)

    def load_chart_profiles(self):
        return list(self.workspace.chart_profiles)


def test_world_graph_and_recent_stats_and_world_analyst():
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = _workspace()
        service = LotteryResearchService(
            repository=WorkspaceRepository(workspace),
            graph_service=FakeGraphService(),
            report_writer=LotteryReportWriter(Path(temp_dir)),
            world_runtime=LotteryWorldRuntime(
                FakeGraphService(),
                store=WorldSessionStore(str(Path(temp_dir) / "world")),
                letta_client=FakeLettaClient(),
            ),
        )
        service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "miss_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=True,
            agent_dialogue_rounds=1,
            live_interview_enabled=False,
            budget_yuan=20,
        )
        session_id = result["world_session"]["session_id"]
        graph = service.get_world_graph(session_id)
        stats = service.get_recent_draw_stats(session_id)
        interview = service.interview_world_agent(session_id, "world_analyst", "Summarize the strongest cluster.")

    assert any(node["node_type"] == "agent" for node in graph["nodes"])
    assert any(node["node_type"] == "phase" for node in graph["nodes"])
    assert any(edge["relation"] == "proposed" for edge in graph["edges"])
    assert any(edge["relation"] == "synthesized_into" for edge in graph["edges"])
    assert len(stats["numbers"]) == 80
    assert stats["window_size"] == 8
    assert stats["numbers"][0]["number"] == 1
    assert "World Analyst" in interview["answer"]


def _workspace() -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 20, "Use Ziwei prompt.", ("prompt",)),
        KnowledgeDocument("basis.md", "knowledge", "knowledge/learn/basis.md", 20, "冷号与命盘都重要。", ("冷号", "命盘")),
        KnowledgeDocument("prediction_report.md", "report", "reports/prediction_report.md", 20, "manual only", ("manual",)),
    )
    strategies = {
        "cold_rule": RuleAgent("cold_rule", "Cold Rule", (1, 2, 3, 4, 5)),
        "miss_rule": RuleAgent("miss_rule", "Miss Rule", (6, 7, 8, 9, 10)),
    }
    completed = tuple(_draw(f"202600{index}", (1, 2, 3, 4, min(index + 4, 12))) for index in range(1, 9))
    return WorkspaceAssets(
        completed_draws=completed,
        pending_draws=(_draw("2026009", ()),),
        knowledge_documents=docs,
        chart_profiles=(),
        strategies=strategies,
        local_workspace_graph=GraphSnapshot("workspace", 1, 1, ("cold",), {"cold": 1.0}, ("basis.md",), 0, ("a->b",)),
        kuzu_graph_status={},
        zep_graph_status={},
    )


def _draw(period: str, numbers: tuple[int, ...]) -> DrawRecord:
    return DrawRecord(
        period=period,
        date="2026-03-16",
        chinese_date="",
        numbers=numbers,
        daily_energy=EnergySignature("甲", "子", ("天机",)),
        hourly_energy=EnergySignature("乙", "丑", ("太阴",)),
    )
