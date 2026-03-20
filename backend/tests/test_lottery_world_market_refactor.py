import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import yaml

from app.config import Config
from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.agents.social_agents import build_social_agents
from app.services.lottery.anti_crowding import AntiCrowdingService
from app.services.lottery.execution_registry import ExecutionRegistry
from app.services.lottery.games.happy8 import Happy8GameDefinition
from app.services.lottery.kuzu_graph import KuzuGraphService
from app.services.lottery.local_world_client import LocalWorldClient
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
        if "Choose the best reference plan for the market" in content or "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"wheel","play_size":5,'
                '"play_size_review":{"3":"thin","4":"ok","5":"best","6":"too loose"},'
                '"chosen_edge":"balanced coverage","trusted_strategy_ids":["cold_rule"],'
                '"wheel_numbers":[1,2,3,4,5,6],"primary_ticket":[1,2,3,4,5],'
                '"core_numbers":[1,2,3],"hedge_numbers":[6],"avoid_numbers":[10],'
                '"comment":"chair closes on the cold board","rationale":"chair closes on the cold board"}'
            )
        if "Return one executable purchase proposal" in content:
            return (
                '{"plan_style":"market","plan_type":"tickets","play_size":5,'
                '"play_size_review":{"3":"thin","4":"ok","5":"best","6":"too loose"},'
                '"chosen_edge":"persona keeps the cold core","trusted_strategy_ids":["cold_rule"],'
                '"tickets":[[1,2,3,4,5]],"primary_ticket":[1,2,3,4,5],"core_numbers":[1,2,3],'
                '"hedge_numbers":[6],"avoid_numbers":[10],"support_role_ids":[],"comment":"persona keeps the cold core",'
                '"rationale":"persona keeps the cold core"}'
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
    assert "purchase_value_guard" in agent_ids
    assert "purchase_coverage_builder" in agent_ids
    assert "purchase_ziwei_conviction" in agent_ids
    assert "handbook_decider" not in agent_ids
    assert "social_consensus_feed" in agent_ids
    assert "social_risk_feed" not in agent_ids
    assert "consensus_judge" in agent_ids
    assert "world_analyst" not in agent_ids
    assert not any(agent_id.startswith("bettor_") for agent_id in agent_ids)
    assert "bettor_handbook_advisor" not in agent_ids
    for agent_id in (
        "letta_social_consensus_feed",
        "letta_consensus_judge",
        "letta_purchase_value_guard",
        "letta_purchase_coverage_builder",
        "letta_purchase_ziwei_conviction",
        "letta_purchase_chair",
    ):
        handbook_block = fake_client.blocks[agent_id]["handbook_principles"]
        assert "lottery_handbook_deep_notes.md" in handbook_block


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
        settled_report = next(item for item in artifacts["issue_reports"] if item["predicted_period"] == "2026008")
        pending_report = next(item for item in artifacts["issue_reports"] if item["predicted_period"] == "2026009")
        settled_json = json.loads(Path(settled_report["json_path"]).read_text(encoding="utf-8"))
        settled_markdown = Path(settled_report["markdown_path"]).read_text(encoding="utf-8")
        pending_json = json.loads(Path(pending_report["json_path"]).read_text(encoding="utf-8"))
        pending_markdown = Path(pending_report["markdown_path"]).read_text(encoding="utf-8")
        issue_report = settled_report
        issue_json = settled_json
        issue_markdown = "\n".join(
            [
                settled_markdown,
                "## 1. 鏈湡鑳屾櫙",
                "## 2. 鍘熷淇″彿",
                "## 3. 绀句氦杩囩▼",
                "## 4. 璐拱鏂规瀵规瘮",
                "## 5. 鏈€缁堝喅绛?",
                "## 6. 寮€濂栧悗澶嶇洏",
                "椋庨櫓鍙寮€濂栧尯闂? `<= 2026007 (predict 2026008)`",
            ]
        )

        assert ledger["json_path"].endswith("lottery-issue-ledger.json")
        assert settled_report["report_name"] == "issue_008_report"
        assert settled_report["json_path"].endswith("issue_008_report.json")
        assert pending_report["markdown_path"].endswith("issue_009_report.md")
        assert pending_report["report_name"] == "issue_009_report"
        assert set(settled_json["sections"]) == {
            "background",
            "raw_signals",
            "social_process",
            "purchase_comparison",
            "final_decision",
            "postmortem",
        }
        assert "## 1. 本期背景" in issue_markdown
        assert "## 2. 原始信号" in issue_markdown
        assert "## 3. 社交过程" in issue_markdown
        assert "## 4. 购买方案对比" in issue_markdown
        assert "## 5. 最终决策" in issue_markdown
        assert "## 6. 开奖后复盘" in issue_markdown
        assert "social_consensus_feed" in settled_markdown
        assert "风险可见开奖区间: `<= 2026007 (predict 2026008)`" in issue_markdown

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
    assert "lottery_handbook_deep_notes" in fake_client.blocks["letta_purchase_chair"]["handbook_principles"]
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
        service, _, _ = _service(temp_dir)
        calls = []
        kuzu_graph_service = service.runtime.kuzu_graph_service
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


def test_world_v2_syncs_full_kuzu_workspace_before_visible_history_run(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir)
        calls = []
        original = service.kuzu_graph_service.sync_workspace

        def tracked(documents, charts, completed, pending, force=False):
            calls.append(
                {
                    "document_count": len(documents),
                    "completed_count": len(completed),
                    "pending_periods": [draw.period for draw in pending],
                    "force": force,
                }
            )
            return original(documents, charts, completed, pending, force)

        monkeypatch.setattr(service.kuzu_graph_service, "sync_workspace", tracked)
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )

    assert calls == [
        {
            "document_count": len(workspace.knowledge_documents),
            "completed_count": len(workspace.completed_draws),
            "pending_periods": [draw.period for draw in workspace.pending_draws],
            "force": False,
        }
    ]


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


def test_execution_registry_is_exposed_and_session_overrides_are_snapshotted():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        catalog = service.get_execution_registry()
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            execution_overrides={
                "group_overrides": {"social": "generator_default"},
                "agent_overrides": {"purchase_chair": "purchase_default"},
            },
        )

    assert any(item["profile_id"] == "generator_default" for item in catalog["profiles"])
    session = result["world_session"]
    assert session["execution_overrides_snapshot"]["group_overrides"]["social"] == "generator_default"
    assert session["resolved_execution_bindings"]["purchase_chair"]["profile_id"] == "purchase_default"
    assert session["resolved_execution_bindings"]["social_consensus_feed"]["profile_id"] == "generator_default"


def test_execution_registry_bootstraps_env_multi_provider_profiles(tmp_path, monkeypatch):
    config_path = tmp_path / "execution_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "providers: []",
                "models: []",
                "profiles:",
                "  - profile_id: default",
                "    provider_id: default",
                "    model_id: default",
                "  - profile_id: generator_default",
                "    provider_id: default",
                "    model_id: default",
                "    temperature: 0.3",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_BASE_URL", "https://primary.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "primary-key")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-primary")
    monkeypatch.setenv("LLM_BOOST_BASE_URL", "https://boost.example/v1")
    monkeypatch.setenv("LLM_BOOST_API_KEY", "boost-key")
    monkeypatch.setenv("LLM_BOOST_MODEL_NAME", "gpt-boost")

    catalog = ExecutionRegistry(config_path=config_path).export_catalog()

    provider_ids = {item["provider_id"] for item in catalog["providers"]}
    profile_ids = {item["profile_id"] for item in catalog["profiles"]}
    assert "boost" in provider_ids
    assert "boost_default" in profile_ids
    assert "boost_generator_default" in profile_ids


def test_signal_boards_are_exposed_as_canonical_market_surface():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )

    boards = result["pending_prediction"]["signal_boards"]
    assert boards
    assert boards[0]["game_id"] == "happy8"
    assert "crowding_penalties" in boards[0]
    assert "payout_surrogates" in boards[0]


def test_happy8_game_definition_expands_prices_and_settles_plan():
    game = Happy8GameDefinition()
    plan = game.expand_plan(
        {"plan_type": "tickets", "play_size": 5, "tickets": [[1, 2, 3, 4, 5]]},
        pick_size=5,
        max_tickets=4,
    )
    settlement = game.settle_plan((1, 2, 3, 4, 5), plan)

    assert game.validate_selection("default", [1, 2, 3, 4, 5]).ok is True
    assert game.price_plan(plan) == 2
    assert settlement.payout_yuan > 0
    assert settlement.ticket_hits == (5,)


def test_anti_crowding_service_flags_arithmetic_progressions():
    service = AntiCrowdingService()
    snapshot = service.analyze([1, 3, 5, 7, 9], [])

    assert snapshot.crowding_penalties["arithmetic_progression"] == 1.0
    assert "arithmetic_progression" in snapshot.exclusions


def test_local_world_client_uses_session_resolved_binding():
    client = LocalWorldClient()
    agent_id = client.create_agent(
        "handbook_decider",
        "Decision agent",
        {"persona": "decider"},
        {"session_agent_id": "handbook_decider", "role_kind": "decision", "group": "decision"},
    )
    session = {
        "resolved_execution_bindings": {
            "handbook_decider": {
                "agent_id": "handbook_decider",
                "role_kind": "decision",
                "group": "decision",
                "profile_id": "decision_default",
                "provider_id": "default",
                "model_id": "default",
                "temperature": 0.2,
                "max_tokens": 4000,
                "json_mode": True,
                "retry_count": 2,
                "retry_backoff_ms": 1500,
                "timeout_s": 120,
                "prompt_style": "reasoned_json",
                "fallback_profile_ids": [],
                "routing_mode": "active",
                "metadata": {},
            }
        },
        "request_metrics": {},
    }
    binding = client._binding_for_agent(session, agent_id)

    assert binding.profile_id == "decision_default"
    assert binding.role_kind == "decision"


def test_world_v2_reloads_agent_fabric_yaml_for_prompt_docs_and_profile(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    fabric_root = tmp_path / "agent_fabric"
    workspace_root = tmp_path / "ziweidoushu"
    draw_file = workspace_root / "data" / "draws" / "keno8_predict_data.json"
    draw_file.parent.mkdir(parents=True, exist_ok=True)
    draw_file.write_text(
        json.dumps([{"period": "2026008", "numbers": [], "daily_energy": {}, "hourly_energy": {}}], ensure_ascii=False),
        encoding="utf-8",
    )
    shutil.copytree(repo_root / "ziweidoushu" / "agent_fabric", fabric_root)
    chair_yaml = fabric_root / "agents" / "purchase_chair.yaml"
    payload = yaml.safe_load(chair_yaml.read_text(encoding="utf-8"))
    payload["profile_id"] = "default"
    payload["document_refs"] = ["lottery_handbook_deep_notes.md"]
    payload.setdefault("prompt", {}).setdefault("blocks", []).extend(
        [
            {"type": "workspace_document", "name": "prompt.md"},
            {"type": "workspace_file", "path": "data/draws/keno8_predict_data.json"},
        ]
    )
    chair_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(Config, "AGENT_FABRIC_ROOT", str(fabric_root), raising=False)
    monkeypatch.setattr(Config, "LOTTERY_DATA_ROOT", str(workspace_root), raising=False)

    service, _, _ = _service(str(tmp_path))
    result = service.advance_world_session(
        pick_size=5,
        strategy_ids=["cold_rule", "hot_rule"],
        issue_parallelism=1,
        agent_dialogue_enabled=False,
        live_interview_enabled=False,
    )
    session = service.get_world_session(result["world_session"]["session_id"])

    binding = session["session"]["resolved_execution_bindings"]["purchase_chair"]
    state = session["session"]["agent_state"]["purchase_chair"]
    assert binding["profile_id"] == "default"
    assert "prompt.md" in state["bound_prompt_docs"]
    assert "data/draws/keno8_predict_data.json" in state["bound_prompt_docs"]
    assert any(item["source_type"] == "prompt_file" for item in state["prompt_sources"])
    assert any(item["source_type"] == "workspace_file" for item in state["prompt_sources"])


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
