import importlib
import json
from pathlib import Path
import sys
import tempfile

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.agents.social_agents import build_social_agents
from app.services.lottery.kuzu_graph import KuzuGraphService
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.research_types import WorkspaceAssets
from app.services.lottery.world_runtime import LotteryWorldRuntime
from app.services.lottery.world_store import WorldSessionStore
from app.services.lottery.world_v2_runtime import _grouped_generator_strategies


class FakeGraphService:
    def build_prediction_graph(self, history, target_draw, documents, charts):
        return GraphSnapshot(
            "prediction",
            3,
            2,
            ("cold", "handbook"),
            {"cold": 2.0, "handbook": 1.5},
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
        self.passages = {}
        self.prompt_log = {}
        self.mcp_servers = {}
        self.attached_tools = {}
        self.send_message_calls = 0

    def create_agent(self, name, description, memory_blocks, metadata=None):
        agent_id = f"letta_{name}"
        self.blocks[agent_id] = dict(memory_blocks)
        self.passages[agent_id] = []
        self.attached_tools[agent_id] = set()
        return agent_id

    def update_block(self, agent_id, block_label, value):
        self.blocks.setdefault(agent_id, {})[block_label] = value

    def add_passage(self, agent_id, text, tags=None):
        self.passages.setdefault(agent_id, []).append({"text": text, "tags": tags or []})

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
        self.send_message_calls += 1
        self.prompt_log[agent_id] = content
        if "accepted_purchase_recommendation" in content:
            return (
                '{"numbers":[1,2,3,4,5],"alternate_numbers":[6,7,8],'
                '"trusted_strategy_ids":["cold_rule"],"adopted_groups":["data","metaphysics"],'
                '"accepted_purchase_recommendation":true,'
                '"rationale":"handbook keeps the cold core and accepts the chair plan.",'
                '"risk_note":"avoid over-crowded tails"}'
            )
        if "Choose one reference plan for the market" in content or "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"wheel","play_size":5,'
                '"play_size_review":{"3":"thin","4":"ok","5":"best","6":"too loose"},'
                '"chosen_edge":"balanced coverage","trusted_strategy_ids":["cold_rule"],'
                '"wheel_numbers":[1,2,3,4,5,6],"primary_ticket":[1,2,3,4,5],'
                '"core_numbers":[1,2,3],"hedge_numbers":[6],"avoid_numbers":[10],'
                '"comment":"chair closes on the cold board","rationale":"chair closes on the cold board"}'
            )
        if '"structure_bias"' in content:
            return (
                '{"numbers":[1,2,3,4,5],"comment":"judge keeps the cold cluster",'
                '"rationale":"cold cluster remains coherent","trusted_strategy_ids":["cold_rule"],'
                '"play_size_bias":5,"structure_bias":"wheel"}'
            )
        if '"highlighted_numbers"' in content:
            return (
                '{"comment":"market feed amplifies the cold core","focus":["cold"],'
                '"trusted_strategy_ids":["cold_rule"],"highlighted_numbers":[1,2,3,4,5],'
                '"support_agent_ids":["cold_rule"],"sentiment":"bullish"}'
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
            rationale=f"{self.display_name} picks the core cluster",
            ranked_scores=tuple((number, 10.0 - index) for index, number in enumerate(self._numbers)),
            kind="rule",
            metadata={},
        )


class GroupRuleAgent(StrategyAgent):
    def __init__(self, strategy_id, display_name, group, numbers):
        super().__init__(strategy_id, display_name, f"{display_name} description", 1, group)
        self._numbers = numbers

    def predict(self, context, pick_size: int) -> StrategyPrediction:
        del pick_size
        return StrategyPrediction(
            strategy_id=self.strategy_id,
            display_name=self.display_name,
            group=self.group,
            numbers=self._numbers,
            rationale=f"{self.display_name} keeps its own isolated board",
            ranked_scores=tuple((number, 10.0 - index) for index, number in enumerate(self._numbers)),
            kind="rule",
            metadata={"seen_peer_count": len(getattr(context, "peer_predictions", {}) or {})},
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


def test_visible_through_period_predicts_next_issue_without_leaking_numbers():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=True,
            agent_dialogue_rounds=5,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )

    pending = result["pending_prediction"]
    assert pending["visible_through_period"] == "2026007"
    assert pending["predicted_period"] == "2026008"
    assert pending["final_decision"]["numbers"] == [1, 2, 3, 4, 5]
    assert result["world_session"]["progress"]["dialogue_round_total"] == 5


def test_second_visible_period_first_settles_then_predicts_next_issue():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        first = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )
        second = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            session_id=first["world_session"]["session_id"],
            visible_through_period="2026008",
        )
        session = service.get_world_session(first["world_session"]["session_id"])

    assert second["pending_prediction"]["predicted_period"] == "2026009"
    assert session["session"]["settlement_history"][-1]["period"] == "2026008"
    assert session["session"]["latest_review"]["period"] == "2026008"
    assert session["session"]["issue_ledger"][-1]["predicted_period"] == "2026008"


def test_market_runtime_keeps_only_expected_agents_and_binds_handbook():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session = service.get_world_session(result["world_session"]["session_id"])

    agent_ids = {item["session_agent_id"] for item in session["session"]["agents"]}
    assert "purchase_chair" in agent_ids
    assert "handbook_decider" in agent_ids
    assert "social_consensus_feed" in agent_ids
    assert "social_risk_feed" in agent_ids
    assert "consensus_judge" in agent_ids
    assert "world_analyst" not in agent_ids
    assert not any(agent_id.startswith("bettor_") for agent_id in agent_ids)
    assert "bettor_handbook_advisor" not in agent_ids
    for agent_id in (
        "letta_social_consensus_feed",
        "letta_social_risk_feed",
        "letta_consensus_judge",
        "letta_purchase_chair",
        "letta_handbook_decider",
    ):
        assert any("lottery_handbook_deep_notes.md" in item["text"] for item in fake_client.passages[agent_id])


def test_world_reports_write_issue_ledger_and_issue_report():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        first = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )
        second = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            session_id=first["world_session"]["session_id"],
            visible_through_period="2026008",
        )
        artifacts = second["report_artifacts"]
        ledger = artifacts["issue_ledger"]
        issue_report = next(item for item in artifacts["issue_reports"] if item["predicted_period"] == "2026008")
        issue_json = json.loads(Path(issue_report["json_path"]).read_text(encoding="utf-8"))
        issue_markdown = Path(issue_report["markdown_path"]).read_text(encoding="utf-8")

        assert ledger["json_path"].endswith("lottery-issue-ledger.json")
        assert issue_report["report_name"] == "issue_008_report"
        assert issue_report["json_path"].endswith("issue_008_report.json")
        assert issue_report["markdown_path"].endswith("issue_008_report.md")
        assert set(issue_json["sections"]) == {
            "background",
            "raw_signals",
            "social_process",
            "purchase_comparison",
            "final_decision",
            "postmortem",
        }
        assert "## 1." in issue_markdown
        assert "## 2." in issue_markdown
        assert "## 3." in issue_markdown
        assert "## 4." in issue_markdown
        assert "## 5." in issue_markdown
        assert "## 6." in issue_markdown

def test_social_layer_stays_small_and_roles_are_distinct():
    agents = build_social_agents()
    assert 1 <= len(agents) <= 6
    modes = [agent.social_mode for agent in agents.values()]
    assert len(modes) == len(set(modes))
    assert set(modes) == {"consensus", "risk"}


def test_generator_groups_are_isolated_before_market_stage(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        tracked_groups = []
        original = service.world_v2_runtime._opening_predictions

        def tracked(context, strategies, pick_size: int, parallelism: int):
            grouped = _grouped_generator_strategies(strategies)
            for group_name, rows in grouped.items():
                if rows:
                    tracked_groups.append((group_name, tuple(rows.keys())))
            return original(context, strategies, pick_size, parallelism)

        monkeypatch.setattr(service.world_v2_runtime, "_opening_predictions", tracked)
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )

    assert tracked_groups == [("data", ("cold_rule", "hot_rule"))]


def test_grouped_generator_strategies_splits_data_metaphysics_and_hybrid():
    strategies = {
        "data_rule": GroupRuleAgent("data_rule", "Data Rule", "data", (1, 2, 3, 4, 5)),
        "meta_rule": GroupRuleAgent("meta_rule", "Meta Rule", "metaphysics", (6, 7, 8, 9, 10)),
        "hybrid_rule": GroupRuleAgent("hybrid_rule", "Hybrid Rule", "hybrid", (11, 12, 13, 14, 15)),
        "social_rule": GroupRuleAgent("social_rule", "Social Rule", "social", (16, 17, 18, 19, 20)),
    }

    grouped = _grouped_generator_strategies(strategies)

    assert list(grouped["data"]) == ["data_rule"]
    assert list(grouped["metaphysics"]) == ["meta_rule"]
    assert list(grouped["hybrid"]) == ["hybrid_rule"]
    assert "social_rule" not in grouped["data"]
    assert "social_rule" not in grouped["metaphysics"]
    assert "social_rule" not in grouped["hybrid"]


def test_opening_predictions_runs_generators_group_by_group(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        strategies = {
            "data_rule": GroupRuleAgent("data_rule", "Data Rule", "data", (1, 2, 3, 4, 5)),
            "meta_rule": GroupRuleAgent("meta_rule", "Meta Rule", "metaphysics", (6, 7, 8, 9, 10)),
            "hybrid_rule": GroupRuleAgent("hybrid_rule", "Hybrid Rule", "hybrid", (11, 12, 13, 14, 15)),
        }
        calls = []

        def tracked(context, stage_strategies, pick_size: int, parallelism: int):
            del context, pick_size, parallelism
            calls.append(tuple((sid, agent.group) for sid, agent in stage_strategies.items()))
            return {
                sid: agent.predict(object(), 5)
                for sid, agent in stage_strategies.items()
            }

        monkeypatch.setattr("app.services.lottery.world_v2_runtime.run_strategy_stage", tracked)
        predictions = service.world_v2_runtime._opening_predictions(object(), strategies, 5, 1)

    assert [tuple(group for _, group in call) for call in calls] == [
        ("data",),
        ("metaphysics",),
        ("hybrid",),
    ]
    assert list(predictions) == ["data_rule", "meta_rule", "hybrid_rule"]


def test_shared_blocks_publish_current_issue_market_and_handbook_context():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )

    shared = result["world_session"]["shared_memory"]
    assert "visible_draw_history_digest" in shared
    assert "market_board" in shared
    assert "social_feed" in shared
    assert "purchase_board" in shared
    assert "handbook_principles" in shared
    assert "final_decision_constraints" in shared
    assert "2026008" in shared["final_decision_constraints"]
    assert "lottery_handbook_deep_notes" in fake_client.blocks["letta_handbook_decider"]["handbook_principles"]
    assert fake_client.blocks["letta_purchase_chair"]["purchase_board"]


def test_app_services_package_uses_lazy_exports(monkeypatch):
    sys.modules.pop("app.services", None)
    services = importlib.import_module("app.services")
    calls = []
    original = services.import_module

    def tracked(module_name, package=None):
        calls.append((module_name, package))
        return original(module_name, package)

    monkeypatch.setattr(services, "import_module", tracked)
    assert "SimulationManager" in services.__all__
    assert calls == []
    assert services.TextProcessor.__name__ == "TextProcessor"
    assert calls == [(".text_processor", "app.services")]


def test_kuzu_csv_payload_omits_header(tmp_path):
    service = KuzuGraphService(db_root=str(tmp_path / "kuzu"))
    csv_path = Path(
        service._write_csv(
            tmp_path / "issues.csv",
            ("id", "period", "text"),
            [("draw:2026001", "2026001", "payload")],
        )
    )
    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "draw:2026001,2026001,payload"
    ]


def test_runtime_projection_flushes_once_per_round(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir)
        calls = []
        kuzu_graph_service = service.runtime.kuzu_graph_service
        kuzu_graph_service.sync_workspace(
            workspace.knowledge_documents,
            workspace.chart_profiles,
            workspace.completed_draws,
            workspace.pending_draws,
            force=True,
        )
        original = kuzu_graph_service.project_runtime_state

        def tracked(session):
            calls.append(str(session.get("current_phase")))
            return original(session)

        monkeypatch.setattr(kuzu_graph_service, "project_runtime_state", tracked)
        first = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )
        assert len(calls) == 1
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            session_id=first["world_session"]["session_id"],
            visible_through_period="2026008",
        )
        assert len(calls) == 3


def test_runtime_projection_skip_is_explicit_when_kuzu_is_unsynced():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        session = service.world_v2_runtime._create_session({}, 5, None, 100)
        service.runtime.kuzu_graph_service.has_synced_workspace = lambda: False  # type: ignore[method-assign]

        service.world_v2_runtime._mark_runtime_projection_dirty(session)
        service.world_v2_runtime._flush_runtime_projection(session)

    assert session["kuzu_runtime_projection_status"] == "skipped"
    assert session["execution_log"][-1]["code"] == "kuzu_runtime_projection_skipped"


def test_agent_result_cache_reuses_same_issue_outputs_across_sessions():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, workspace = _service(temp_dir)
        service.runtime.kuzu_graph_service.sync_workspace(
            workspace.knowledge_documents,
            workspace.chart_profiles,
            workspace.completed_draws,
            workspace.pending_draws,
            force=True,
        )
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
            session_id="cache-a",
        )
        first_calls = fake_client.send_message_calls
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
            session_id="cache-b",
        )

    assert first_calls > 0
    assert fake_client.send_message_calls == first_calls


def _service(temp_dir: str):
    workspace = _workspace()
    graph_service = FakeGraphService()
    kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
    world_runtime = LotteryWorldRuntime(
        graph_service,
        store=WorldSessionStore(str(Path(temp_dir) / "world")),
        letta_client=FakeLettaClient(),
        kuzu_graph_service=kuzu_graph_service,
    )
    service = LotteryResearchService(
        repository=WorkspaceRepository(workspace),
        graph_service=graph_service,
        kuzu_graph_service=kuzu_graph_service,
        report_writer=LotteryReportWriter(Path(temp_dir)),
        world_runtime=world_runtime,
    )
    service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
    return service, world_runtime.letta_client, workspace


def _workspace() -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 40, "Use market format.", ("prompt",)),
        KnowledgeDocument(
            "lottery_handbook_deep_notes.md",
            "prompt",
            "knowledge/prompts/lottery_handbook_deep_notes.md",
            120,
            "Handbook doctrine: avoid crowding and reduce shared-prize dilution.",
            ("handbook", "anti_crowding"),
        ),
        KnowledgeDocument(
            "basis.md",
            "knowledge",
            "knowledge/learn/basis.md",
            40,
            "Cold numbers and omission trends are important.",
            ("cold", "omission"),
        ),
    )
    strategies = {
        "cold_rule": RuleAgent("cold_rule", "Cold Rule", (1, 2, 3, 4, 5)),
        "hot_rule": RuleAgent("hot_rule", "Hot Rule", (6, 7, 8, 9, 10)),
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
        date="2026-03-15",
        chinese_date="",
        numbers=numbers,
        daily_energy=EnergySignature("jia", "zi", ("tianji",)),
        hourly_energy=EnergySignature("yi", "chou", ("taiyin",)),
    )
