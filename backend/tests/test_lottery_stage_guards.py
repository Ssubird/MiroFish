from pathlib import Path
import tempfile

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.backtest_policy import select_strategies
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.research_types import WorkspaceAssets
from app.services.lottery.world_runtime import LotteryWorldRuntime
from app.services.lottery.world_store import WorldSessionStore
from app.services.lottery.world_v2_runtime import AGENT_BLOCK_SCHEMA_VERSION, _session_compatible


class FakeGraphService:
    def build_prediction_graph(self, history, target_draw, documents, charts):
        return GraphSnapshot("prediction", 1, 1, ("cold",), {"cold": 1.0}, ("basis.md",), len(charts), ("a->b",))

    def build_workspace_graph(self, documents, charts, completed_draws, pending_draw):
        return GraphSnapshot("workspace", 1, 1, ("cold",), {"cold": 1.0}, ("basis.md",), len(charts), ("a->b",))


class FakeLettaClient:
    def create_agent(self, name, description, memory_blocks, metadata=None):
        return f"letta_{name}"

    def update_block(self, agent_id, block_label, value):
        return None

    def add_passage(self, agent_id, text, tags=None):
        return None

    def send_message(self, agent_id, content):
        if "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"tickets","play_size":5,'
                '"play_size_review":{"3":"thin","4":"ok","5":"best","6":"diffuse"},'
                '"chosen_edge":"chair keeps the core five","tickets":[[1,2,3,4,5]],'
                '"primary_ticket":[1,2,3,4,5],"rationale":"chair"}'
            )
        if "Return one executable purchase proposal" in content or any(
            name in agent_id
            for name in (
                "budget_guard",
                "coverage_builder",
                "upside_hunter",
                "purchase_value_guard",
                "purchase_coverage_builder",
                "purchase_ziwei_conviction",
            )
        ):
            return (
                '{"plan_style":"committee","plan_type":"tickets","play_size":5,'
                '"play_size_review":{"3":"thin","4":"ok","5":"best","6":"diffuse"},'
                '"chosen_edge":"member keeps the core five","tickets":[[1,2,3,4,5]],'
                '"primary_ticket":[1,2,3,4,5],"rationale":"member"}'
            )
        if "Reply publicly" in content:
            return '{"numbers":[1,2,3,4,5],"comment":"debate post","support_agent_ids":[],"rationale":"stay"}'
        return '{"comment":"postmortem","focus":["cold"],"trusted_strategy_ids":["primary_rule"]}'


class RuleAgent(StrategyAgent):
    kind = "rule"
    uses_llm = False
    default_enabled = True

    def __init__(self, strategy_id, display_name, description, required_history, group, numbers=(1, 2, 3, 4, 5)):
        super().__init__(strategy_id, display_name, description, required_history, group)
        self._numbers = tuple(numbers)

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=self._numbers,
            rationale="rule picks",
            ranked_scores=tuple((number, 6.0 - index) for index, number in enumerate(self._numbers[:2])),
            kind="rule",
            metadata={},
        )


class DisabledRuleAgent(RuleAgent):
    default_enabled = False


def test_world_v1_registers_generators_without_social_or_judge_amplifiers():
    with tempfile.TemporaryDirectory() as temp_dir:
        service = _service(
            temp_dir,
                {
                    "primary_rule": RuleAgent("primary_rule", "Primary Rule", "primary", 1, "data"),
                    "hybrid_rule": RuleAgent("hybrid_rule", "Hybrid Rule", "hybrid", 1, "hybrid", (6, 7, 8, 9, 10)),
                },
            )
        result = service.run_backtest(
            evaluation_size=1,
            pick_size=5,
            strategy_ids=["primary_rule", "hybrid_rule"],
            runtime_mode="world_v1",
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )

    agent_ids = {item["session_agent_id"] for item in result["world_session"]["agents"]}
    assert "primary_rule" in agent_ids
    assert "hybrid_rule" in agent_ids
    assert "purchase_chair" in agent_ids
    assert "world_judge" not in agent_ids
    assert "rule_interpreter" not in agent_ids


def test_select_strategies_without_ids_returns_default_enabled_only():
    strategies = {
        "primary_rule": RuleAgent("primary_rule", "Primary Rule", "primary", 1, "data"),
        "full_context_rule": DisabledRuleAgent("full_context_rule", "Full Context", "full", 1, "metaphysics"),
        "hybrid_rule": RuleAgent("hybrid_rule", "Hybrid Rule", "hybrid", 1, "hybrid"),
    }

    selected = select_strategies(strategies, None)

    assert list(selected) == ["primary_rule", "hybrid_rule"]


def test_select_strategies_can_explicitly_include_default_disabled_agent():
    strategies = {
        "primary_rule": RuleAgent("primary_rule", "Primary Rule", "primary", 1, "data"),
        "full_context_rule": DisabledRuleAgent("full_context_rule", "Full Context", "full", 1, "metaphysics"),
    }

    selected = select_strategies(strategies, ["primary_rule", "full_context_rule"])

    assert list(selected) == ["primary_rule", "full_context_rule"]


def test_select_strategies_ignores_retired_world_amplifiers():
    strategies = {
        "primary_rule": RuleAgent("primary_rule", "Primary Rule", "primary", 1, "data"),
        "hybrid_rule": RuleAgent("hybrid_rule", "Hybrid Rule", "hybrid", 1, "hybrid"),
    }

    selected = select_strategies(
        strategies,
        [
            "social_consensus_feed",
            "rule_analyst_feed",
            "primary_rule",
        ],
    )

    assert list(selected) == ["primary_rule"]


def test_world_v2_session_compatible_requires_exact_strategy_set():
    session = {
        "agent_block_schema_version": AGENT_BLOCK_SCHEMA_VERSION,
        "selected_strategy_ids": ["primary_rule"],
        "agents": [],
    }
    strategies = {
        "primary_rule": RuleAgent("primary_rule", "Primary Rule", "primary", 1, "data"),
        "full_context_rule": DisabledRuleAgent("full_context_rule", "Full Context", "full", 1, "metaphysics"),
    }

    assert _session_compatible(session, strategies) is False


def _service(temp_dir: str, strategies: dict[str, StrategyAgent]):
    workspace = _workspace(strategies)
    world_runtime = LotteryWorldRuntime(
        FakeGraphService(),
        store=WorldSessionStore(str(Path(temp_dir) / "world")),
        letta_client=FakeLettaClient(),
    )
    service = LotteryResearchService(
        repository=WorkspaceRepository(workspace),
        graph_service=FakeGraphService(),
        report_writer=LotteryReportWriter(Path(temp_dir)),
        world_runtime=world_runtime,
    )
    service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
    return service


class WorkspaceRepository:
    def __init__(self, workspace: WorkspaceAssets):
        self.workspace = workspace

    def load_draws(self):
        return [*self.workspace.completed_draws, *self.workspace.pending_draws]

    def load_knowledge_documents(self):
        return list(self.workspace.knowledge_documents)

    def load_chart_profiles(self):
        return list(self.workspace.chart_profiles)


def _workspace(strategies: dict[str, StrategyAgent]) -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 10, "Use fixed 5+3.", ("prompt",)),
        KnowledgeDocument("basis.md", "knowledge", "knowledge/learn/basis.md", 10, "cold trend", ("cold",)),
        KnowledgeDocument(
            "prediction_report.md",
            "report",
            "reports/prediction_report.md",
            10,
            "cold stable",
            ("cold",),
            {"created_at": "2026-03-15T08:00:00", "effective_period": "2026006", "max_visible_period": "2026007"},
        ),
    )
    completed = tuple(_draw(f"202600{index}", (1, 2, 3, 4, min(index + 4, 12))) for index in range(1, 8))
    pending = (_draw("2026008", ()),)
    return WorkspaceAssets(
        completed_draws=completed,
        pending_draws=pending,
        knowledge_documents=docs,
        chart_profiles=(),
        strategies=strategies,
        local_workspace_graph=GraphSnapshot("workspace", 1, 1, ("cold",), {"cold": 1.0}, ("prediction_report.md",), 0, ("a->b",)),
        kuzu_graph_status={},
        zep_graph_status={},
    )


def _draw(period: str, numbers: tuple[int, ...]) -> DrawRecord:
    return DrawRecord(
        period=period,
        date="2026-03-15",
        chinese_date="",
        numbers=numbers,
        daily_energy=EnergySignature("甲", "子", ("天机",)),
        hourly_energy=EnergySignature("乙", "丑", ("太阴",)),
    )
