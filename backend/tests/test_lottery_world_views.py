from pathlib import Path
import tempfile

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.kuzu_graph import KuzuGraphService
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
            ("cold", "命盘"),
            {"cold": 2.0, "命盘": 1.5},
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
    TOOL_NAMES = {
        "happy8_rules_mcp": ("validate_plan", "price_plan"),
        "world_state_mcp": ("publish_post", "update_trust"),
        "kuzu_market_mcp": ("search_docs", "top_influencers"),
        "report_memory_mcp": ("report_digest", "find_report_evidence"),
    }

    def __init__(self):
        self.blocks = {}
        self.mcp_servers = {}
        self.attached_tools = {}

    def create_agent(self, name, description, memory_blocks, metadata=None):
        agent_id = f"letta_{name}"
        self.blocks[agent_id] = dict(memory_blocks)
        self.attached_tools[agent_id] = set()
        return agent_id

    def update_block(self, agent_id, block_label, value):
        self.blocks.setdefault(agent_id, {})[block_label] = value

    def add_passage(self, agent_id, text, tags=None):
        return None

    def list_mcp_servers(self):
        return [{"server_name": name} for name in self.mcp_servers]

    def add_mcp_server(self, config):
        self.mcp_servers[config["server_name"]] = dict(config)
        return dict(config)

    def connect_mcp_server(self, config):
        self.mcp_servers[config["server_name"]] = dict(config)
        return dict(config)

    def resync_mcp_server_tools(self, server_name, agent_id=None):
        return {"server_name": server_name, "agent_id": agent_id}

    def list_mcp_tools_by_server(self, server_name):
        return [
            {"id": f"{server_name}:{name}", "name": name}
            for name in self.TOOL_NAMES.get(server_name, ())
        ]

    def list_tools_for_agent(self, agent_id):
        return [{"id": tool_id} for tool_id in sorted(self.attached_tools.get(agent_id, set()))]

    def attach_tool_to_agent(self, agent_id, tool_id):
        self.attached_tools.setdefault(agent_id, set()).add(tool_id)
        return {"agent_id": agent_id, "tool_id": tool_id}

    def send_message(self, agent_id, content):
        if "Answer as the world analyst" in content:
            return "World Analyst: the strongest cluster is still 1/2/3/4/5."
        if "accepted_purchase_recommendation" in content or "handbook_decider" in agent_id:
            return (
                '{"numbers":[1,2,3,4,5],"alternate_numbers":[6,7,8],'
                '"trusted_strategy_ids":["cold_rule"],"adopted_groups":["data"],'
                '"accepted_purchase_recommendation":true,'
                '"rationale":"handbook keeps the cold core and accepts the chair plan.",'
                '"risk_note":"avoid over-crowded tails"}'
            )
        if "Choose the best reference plan for the market" in content or "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"portfolio","play_size":4,'
                '"play_size_review":{"3":"low edge","4":"best","5":"too concentrated","6":"too loose"},'
                '"chosen_edge":"split coverage","portfolio_legs":[{"plan_type":"tickets","play_size":4,"tickets":[[1,2,3,4]],'
                '"primary_ticket":[1,2,3,4],"comment":"base leg","rationale":"base leg"}],'
                '"primary_ticket":[1,2,3,4],"core_numbers":[1,2,3],"hedge_numbers":[4,5],'
                '"avoid_numbers":[10],"trusted_strategy_ids":["cold_rule"],"comment":"chair closes","rationale":"chair closes"}'
            )
        if "Return one executable purchase proposal" in content:
            return (
                '{"plan_style":"market","plan_type":"tickets","play_size":4,'
                '"play_size_review":{"3":"thin","4":"best","5":"too tight","6":"too diffuse"},'
                '"chosen_edge":"cover core four","tickets":[[1,2,3,4]],"primary_ticket":[1,2,3,4],'
                '"core_numbers":[1,2,3],"hedge_numbers":[4,5],"avoid_numbers":[10],"support_role_ids":[],"trusted_strategy_ids":["cold_rule"],'
                '"comment":"keep four-core","rationale":"keep four-core"}'
            )
        if '"structure_bias"' in content:
            return (
                '{"numbers":[1,2,3,4,5],"comment":"judge keeps cold cluster","rationale":"cold remains",'
                '"trusted_strategy_ids":["cold_rule"],"play_size_bias":4,"structure_bias":"tickets"}'
            )
        if '"highlighted_numbers"' in content:
            return (
                '{"comment":"social feed reinforces the cold board","focus":["cold"],"trusted_strategy_ids":["cold_rule"],'
                '"highlighted_numbers":[1,2,3,4,5],"support_agent_ids":["cold_rule"],"sentiment":"bullish"}'
            )
        return '{"comment":"postmortem note","focus":["cold"],"trusted_strategy_ids":["cold_rule"]}'


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
        kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
        service = LotteryResearchService(
            repository=WorkspaceRepository(workspace),
            graph_service=FakeGraphService(),
            kuzu_graph_service=kuzu_graph_service,
            report_writer=LotteryReportWriter(Path(temp_dir)),
            world_runtime=LotteryWorldRuntime(
                FakeGraphService(),
                store=WorldSessionStore(str(Path(temp_dir) / "world")),
                letta_client=FakeLettaClient(),
                kuzu_graph_service=kuzu_graph_service,
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
        interview = service.interview_world_agent(session_id, "purchase_chair", "Summarize the strongest cluster.")

    assert any(node["node_type"] == "agent" for node in graph["nodes"])
    assert any(node["node_type"] == "phase" for node in graph["nodes"])
    assert any(edge["relation"] == "proposed" for edge in graph["edges"])
    assert any(edge["relation"] == "purchased_from" for edge in graph["edges"])
    assert len(stats["numbers"]) == 80
    assert stats["window_size"] == 8
    assert stats["numbers"][0]["number"] == 1
    assert '"primary_ticket":[1,2,3,4]' in interview["answer"]


def _workspace() -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 20, "Use Ziwei prompt.", ("prompt",)),
        KnowledgeDocument(
            "lottery_handbook_deep_notes.md",
            "prompt",
            "knowledge/prompts/lottery_handbook_deep_notes.md",
            40,
            "Handbook doctrine: avoid crowding and preserve executable choices.",
            ("handbook", "crowding"),
        ),
        KnowledgeDocument("basis.md", "knowledge", "knowledge/learn/basis.md", 20, "冷号与命盘都重要。", ("冷号", "命盘")),
        KnowledgeDocument("prediction_report.md", "report", "reports/prediction_report.md", 20, "report evidence", ("report",)),
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
