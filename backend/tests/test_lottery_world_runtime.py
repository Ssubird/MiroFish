from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.catalog import build_market_v2_catalog
from app.services.lottery.kuzu_graph import KuzuGraphService
from app.services.lottery.local_world_client import LocalWorldClient
from app.services.lottery.market_diversity import build_bettor_prompt_view
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.research_types import WorkspaceAssets
from app.services.lottery.world_runtime import LotteryWorldRuntime
from app.services.lottery.world_store import WorldSessionStore
from app.services.lottery.world_support import parse_json_response, prompt_passages, report_passages
from app.services.lottery.world_v2_market import aggregate_number_scores


class FakeGraphService:
    def build_prediction_graph(self, history, target_draw, documents, charts):
        return GraphSnapshot(
            "prediction",
            2,
            1,
            ("cold",),
            {"cold": 1.0},
            tuple(item.name for item in documents),
            len(charts),
            ("cold->trend",),
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
        self.mcp_servers = {}
        self.attached_tools = {}

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
        if "External interview question" in content:
            return "Cold Rule currently stays with [1, 2, 3, 4, 5]."
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
                '{"plan_style":"balanced","plan_type":"wheel","play_size":5,'
                '"play_size_review":{"3":"too thin","4":"acceptable","5":"best balance","6":"too diffuse"},'
                '"chosen_edge":"balanced coverage on the strongest five plus one hedge",'
                '"trusted_strategy_ids":["cold_rule"],"wheel_numbers":[1,2,3,4,5,6],'
                '"primary_ticket":[1,2,3,4,5],"core_numbers":[1,2,3],"hedge_numbers":[6],'
                '"avoid_numbers":[10],"comment":"chair closes on balanced wheel",'
                '"rationale":"chair closes on balanced wheel"}'
            )
        if "Return one executable purchase proposal" in content:
            return (
                '{"plan_style":"market","plan_type":"tickets","play_size":5,'
                '"play_size_review":{"3":"too defensive","4":"still light","5":"fits main consensus","6":"too loose"},'
                '"chosen_edge":"fits persona budget","trusted_strategy_ids":["cold_rule"],'
                '"tickets":[[1,2,3,4,5]],"primary_ticket":[1,2,3,4,5],'
                '"core_numbers":[1,2,3],"hedge_numbers":[6],"avoid_numbers":[10],'
                '"support_role_ids":[],"comment":"keep the strongest five","rationale":"keep the strongest five"}'
            )
        if '"structure_bias"' in content:
            return (
                '{"numbers":[1,2,3,4,5],"comment":"judge keeps the cold cluster",'
                '"rationale":"cold cluster remains coherent","trusted_strategy_ids":["cold_rule"],'
                '"play_size_bias":5,"structure_bias":"tickets"}'
            )
        if '"highlighted_numbers"' in content:
            return (
                '{"comment":"social feed amplifies cold numbers","focus":["cold"],'
                '"trusted_strategy_ids":["cold_rule"],"highlighted_numbers":[1,2,3,4,5],'
                '"support_agent_ids":["cold_rule"],"sentiment":"bullish"}'
            )
        return '{"comment":"postmortem note","focus":["cold"],"trusted_strategy_ids":["cold_rule"]}'


class BrokenPurchaseLettaClient(FakeLettaClient):
    def send_message(self, agent_id, content):
        if "Choose the best reference plan for the market" in content or "purchase_chair" in agent_id:
            return '{"plan_style":"broken","primary_ticket":[1,2,3,4,5],"rationale":"missing plan_type"}'
        return super().send_message(agent_id, content)


class RepairingPurchaseLettaClient(FakeLettaClient):
    def __init__(self):
        super().__init__()
        self._chair_calls = 0

    def send_message(self, agent_id, content):
        if "Validation failed for your previous purchase plan" in content:
            return super().send_message(agent_id, content)
        if "Choose the best reference plan for the market" in content or "purchase_chair" in agent_id:
            self._chair_calls += 1
            if self._chair_calls == 1:
                return (
                    '{"plan_style":"broken","plan_type":"portfolio","portfolio_legs":['
                    '{"plan_type":"tickets","play_size":5,"tickets":'
                    '[[1,2,3,4,5],[1,2,3,4,6],[1,2,3,4,7],[1,2,3,5,6],[1,2,4,5,6]]},'
                    '{"plan_type":"wheel","play_size":5,"wheel_numbers":[1,2,3,4,5,6,7]}],'
                    '"primary_ticket":[1,2,3,4,5],"rationale":"mixed but over budget"}'
                )
        return super().send_message(agent_id, content)


class UnsupportedStdioLettaClient(FakeLettaClient):
    def add_mcp_server(self, config):
        raise RuntimeError(
            'Letta request failed: HTTP 400 {"detail":"stdio is not supported in the current environment, '
            'please use a self-hosted Letta server in order to add a stdio MCP server"}'
        )


class NoMcpFakeLettaClient(FakeLettaClient):
    base_url = "http://127.0.0.1:8283/v1"
    mcp_disabled = True
    runtime_backend = "letta_no_mcp"


class CapturePromptLettaClient(NoMcpFakeLettaClient):
    def __init__(self):
        super().__init__()
        self.prompt_log = {}

    def send_message(self, agent_id, content):
        self.prompt_log[agent_id] = content
        return super().send_message(agent_id, content)


class PassageLimitLettaClient(CapturePromptLettaClient):
    MAX_PASSAGE_CHARS = 3000

    def add_passage(self, agent_id, text, tags=None):
        if len(text) > self.MAX_PASSAGE_CHARS:
            raise RuntimeError(
                "Letta request failed: HTTP 400 "
                '{"detail":"INVALID_ARGUMENT: Archival memory content exceeds token limit of 8192 tokens"}'
            )
        return super().add_passage(agent_id, text, tags)


class StrictBlockNoMcpLettaClient(NoMcpFakeLettaClient):
    def update_block(self, agent_id, block_label, value):
        blocks = self.blocks.setdefault(agent_id, {})
        if block_label not in blocks:
            raise RuntimeError(f"No block with label {block_label!r} found for agent {agent_id}")
        blocks[block_label] = value


class DuplicateBettorLettaClient(FakeLettaClient):
    def __init__(self):
        super().__init__()
        self._bettor_calls = 0

    def send_message(self, agent_id, content):
        if "Return one executable purchase proposal" in content:
            self._bettor_calls += 1
            if self._bettor_calls == 1:
                return (
                    '{"plan_style":"broken","plan_type":"portfolio","portfolio_legs":['
                    '{"plan_type":"tickets","play_size":5,"tickets":[[62,28,49,78,62]],'
                    '"primary_ticket":[62,28,49,78,62],"comment":"duplicate ticket","rationale":"duplicate ticket"}],'
                    '"rationale":"duplicate bettor plan"}'
                )
        return super().send_message(agent_id, content)


def _local_world_response(self, session, agent_id, content):
    del self, session
    if "External interview question" in content:
        return "Cold Rule currently stays with [1, 2, 3, 4, 5]."
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
            '{"plan_style":"balanced","plan_type":"wheel","play_size":5,'
            '"play_size_review":{"3":"too thin","4":"acceptable","5":"best balance","6":"too diffuse"},'
            '"chosen_edge":"balanced coverage on the strongest five plus one hedge",'
            '"trusted_strategy_ids":["cold_rule"],"wheel_numbers":[1,2,3,4,5,6],'
            '"primary_ticket":[1,2,3,4,5],"core_numbers":[1,2,3],"hedge_numbers":[6],'
            '"avoid_numbers":[10],"comment":"chair closes on balanced wheel",'
            '"rationale":"chair closes on balanced wheel"}'
        )
    if "Return one executable purchase proposal" in content:
        return (
            '{"plan_style":"market","plan_type":"tickets","play_size":5,'
            '"play_size_review":{"3":"too defensive","4":"still light","5":"fits main consensus","6":"too loose"},'
            '"chosen_edge":"fits persona budget","trusted_strategy_ids":["cold_rule"],'
            '"tickets":[[1,2,3,4,5]],"primary_ticket":[1,2,3,4,5],'
            '"core_numbers":[1,2,3],"hedge_numbers":[6],"avoid_numbers":[10],'
            '"support_role_ids":[],"comment":"keep the strongest five","rationale":"keep the strongest five"}'
        )
    if '"structure_bias"' in content:
        return (
            '{"numbers":[1,2,3,4,5],"comment":"judge keeps the cold cluster",'
            '"rationale":"cold cluster remains coherent","trusted_strategy_ids":["cold_rule"],'
            '"play_size_bias":5,"structure_bias":"tickets"}'
        )
    if '"highlighted_numbers"' in content:
        return (
            '{"comment":"social feed amplifies cold numbers","focus":["cold"],'
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
            rationale=f"{self.display_name} picks cold trend",
            ranked_scores=tuple((number, 10.0 - index) for index, number in enumerate(self._numbers)),
            kind="rule",
            metadata={},
        )


class WorkspaceRepository:
    def __init__(self, workspace: WorkspaceAssets):
        self.workspace = workspace

    def load_draws(self):
        return [*self.workspace.completed_draws, *self.workspace.pending_draws]

    def load_knowledge_documents(self):
        return list(self.workspace.knowledge_documents)

    def load_chart_profiles(self):
        return list(self.workspace.chart_profiles)


def test_world_advance_uses_market_runtime_and_projects_market_payload():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )
        session = service.get_world_session(result["world_session"]["session_id"])

    pending = result["pending_prediction"]
    assert result["evaluation"]["runtime_mode"] == "world_v2_market"
    assert result["world_session"]["status"] == "await_result"
    assert pending["purchase_recommendation"]["plan_type"] == "wheel"
    assert pending["purchase_recommendation"]["play_size"] == 5
    assert pending["purchase_recommendation"]["status"] == "ready"
    assert len(pending["generator_boards"]) == 2
    assert pending["final_decision"]["numbers"] == [1, 2, 3, 4, 5]
    assert pending["final_decision"]["accepted_purchase_recommendation"] is True
    assert pending["market_discussion"]["social_posts"]
    assert pending["market_discussion"]["judge_boards"] == []
    assert not any(item["event_type"] == "market_rank" for item in pending["world_timeline_preview"])
    assert any(item["event_type"] == "purchase_decision" for item in pending["world_timeline_preview"])
    assert any(item["event_type"] == "official_prediction" for item in pending["world_timeline_preview"])
    agent_ids = {item["session_agent_id"] for item in session["session"]["agents"]}
    assert "purchase_chair" in agent_ids
    assert "purchase_value_guard" in agent_ids
    assert "purchase_coverage_builder" in agent_ids
    assert "purchase_ziwei_conviction" in agent_ids
    assert "handbook_decider" not in agent_ids
    assert "consensus_judge" not in agent_ids
    assert "social_consensus_feed" in agent_ids
    assert "social_risk_feed" not in agent_ids
    assert "world_analyst" not in agent_ids
    assert not any(agent_id.startswith("bettor_") for agent_id in agent_ids)
    assert "happy8_rules_mcp" in fake_client.mcp_servers
    assert session["session"]["latest_purchase_plan"]["ticket_count"] >= 1


def test_market_v2_catalog_ships_purchase_mainline_only():
    catalog = build_market_v2_catalog()

    assert "consensus_judge" not in catalog
    assert "risk_guard_judge" not in catalog


def test_bettor_prompt_view_is_persona_specific():
    strategy_groups = {"cold_rule": "data", "meta_rule": "metaphysics"}
    signal_outputs = [
        {"strategy_id": "cold_rule", "number_scores": {"1": 9.0, "2": 8.0, "3": 7.0, "4": 6.0, "5": 5.0}},
        {"strategy_id": "meta_rule", "number_scores": {"1": 8.5, "8": 7.5, "9": 6.5, "10": 5.5, "11": 4.5}},
    ]
    social_posts = [
        {
            "actor_id": "social_consensus_feed",
            "actor_display_name": "Consensus Feed",
            "content": "The market likes 1 and 2.",
            "numbers": [1, 2, 3, 4, 5],
        },
        {
            "actor_id": "social_risk_feed",
            "actor_display_name": "Risk Feed",
            "content": "1 is too crowded.",
            "numbers": [8, 9, 10, 11],
        },
    ]
    market_ranks = [
        {
            "actor_id": "consensus_judge",
            "actor_display_name": "Consensus Judge",
            "content": "Judge still leans to 1.",
            "numbers": [1, 2, 8, 9, 10],
        }
    ]

    follower = build_bettor_prompt_view(
        "bettor_follower",
        signal_outputs,
        social_posts,
        market_ranks,
        strategy_groups,
    )
    contrarian = build_bettor_prompt_view(
        "bettor_contrarian",
        signal_outputs,
        social_posts,
        market_ranks,
        strategy_groups,
    )

    assert follower["signal_board"] != contrarian["signal_board"]
    assert "crowd leaders" in follower["instruction"]
    assert "Avoid the crowded core" in contrarian["instruction"]


def test_aggregate_number_scores_does_not_overweight_repeated_identical_tickets():
    single = {
        "bettor_follower": {
            "expanded_tickets": [[1, 2, 3, 4, 5]],
            "legs": [{"numbers": [1, 2, 3, 4, 5]}],
        }
    }
    repeated = {
        "bettor_follower": {
            "expanded_tickets": [[1, 2, 3, 4, 5]] * 12,
            "legs": [{"numbers": [1, 2, 3, 4, 5]}],
            "total_cost_yuan": 24,
        }
    }

    single_scores = aggregate_number_scores([], [], [], single)
    repeated_scores = aggregate_number_scores([], [], [], repeated)

    assert repeated_scores[1] == pytest.approx(single_scores[1])
    assert repeated_scores[5] == pytest.approx(single_scores[5])


def test_world_interview_updates_timeline_and_shared_memory():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )
        session_id = result["world_session"]["session_id"]
        before = service.get_world_timeline(session_id, 0, 200)["total"]
        interview = service.interview_world_agent(session_id, "cold_rule", "Why keep following cold numbers?")
        after = service.get_world_timeline(session_id, 0, 200)
        session = service.get_world_session(session_id)

    assert "Cold Rule currently stays with [1, 2, 3, 4, 5]" in interview["answer"]
    assert after["total"] == before + 1
    assert after["items"][-1]["event_type"] == "external_interview"
    assert session["session"]["shared_memory"]["current_issue"]


def test_world_budget_updates_shared_memory_and_session():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            budget_yuan=20,
        )

    assert result["evaluation"]["budget_yuan"] == 20
    assert result["world_session"]["budget_yuan"] == 20
    assert result["world_session"]["shared_memory"]["purchase_budget"] == "Current purchase budget: 20 yuan."


def test_world_payload_preserves_agent_dialogue_enabled_flag():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )

    assert result["evaluation"]["agent_dialogue_enabled"] is False


def test_world_advance_can_run_in_explicit_no_mcp_mode(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setattr(LocalWorldClient, "send_message_for_session", _local_world_response)
    monkeypatch.setattr(
        "app.services.lottery.research_service._no_mcp_world_v2_client",
        lambda: LocalWorldClient(),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = _workspace()
        graph_service = FakeGraphService()
        kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
        world_runtime = LotteryWorldRuntime(
            graph_service,
            store=WorldSessionStore(str(Path(temp_dir) / "world")),
            letta_client=None,
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
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )

    assert result["world_session"]["status"] == "await_result"
    assert result["world_session"]["request_metrics"]["send_message"] > 0
    assert any(item["code"] == "local_no_mcp_mode" for item in result["execution_log"])


def test_world_advance_can_run_with_letta_and_kuzu_without_mcp():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir, NoMcpFakeLettaClient())
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )

    assert result["world_session"]["status"] == "await_result"
    assert any(item["code"] == "letta_no_mcp_mode" for item in result["execution_log"])


def test_world_advance_with_strict_letta_blocks_updates_shared_memory():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, _ = _service(temp_dir, StrictBlockNoMcpLettaClient())
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session = service.get_world_session(result["world_session"]["session_id"])

    assert result["world_session"]["status"] == "await_result"
    for agent in session["session"]["agents"]:
        if agent["letta_agent_id"] == "-":
            continue
        blocks = fake_client.blocks[agent["letta_agent_id"]]
        assert "report_digest" in blocks
        assert "rule_digest" in blocks
        assert blocks["current_issue"]


def test_world_binds_full_prompt_assets_to_purchase_chair():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, _ = _service(temp_dir, CapturePromptLettaClient())
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session = service.get_world_session(result["world_session"]["session_id"])

    agent_ids = {item["session_agent_id"] for item in session["session"]["agents"]}
    passages = fake_client.passages["letta_purchase_chair"]
    handbook_prompt = fake_client.prompt_log["letta_purchase_chair"]
    handbook_block = fake_client.blocks["letta_purchase_chair"]["handbook_principles"]

    assert "handbook_decider" not in agent_ids
    assert "purchase_chair" in agent_ids
    assert "lottery_handbook_deep_notes.md" in handbook_block
    assert "lottery_handbook_deep_notes" in handbook_block
    assert "Choose the best reference plan for the market" in handbook_prompt
    assert result["pending_prediction"]["final_decision"]["numbers"] == [1, 2, 3, 4, 5]


def test_world_chunks_large_bound_prompt_passages_for_purchase_chair_limits():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, fake_client, workspace = _service(temp_dir, PassageLimitLettaClient())
        large_docs = []
        for item in workspace.knowledge_documents:
            if item.name != "lottery_handbook_deep_notes.md":
                large_docs.append(item)
                continue
            large_docs.append(
                replace(
                    item,
                    content=("Anti-crowding handbook section.\n\n" * 900),
                    char_count=len("Anti-crowding handbook section.\n\n" * 900),
                )
            )
        large_workspace = replace(workspace, knowledge_documents=tuple(large_docs))
        service.runtime.load_workspace = lambda: large_workspace  # type: ignore[method-assign]
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session = service.get_world_session(result["world_session"]["session_id"])
        timeline = service.get_world_timeline(result["world_session"]["session_id"], 0, 200)

    passages = fake_client.passages["letta_purchase_chair"]
    state = session["session"]["agent_state"]["purchase_chair"]
    registration = next(
        item for item in timeline["items"] if item["event_type"] == "agent_registered" and item["actor_id"] == "purchase_chair"
    )

    assert result["world_session"]["status"] == "await_result"
    assert len(passages) > 1
    assert all(len(item["text"]) <= PassageLimitLettaClient.MAX_PASSAGE_CHARS for item in passages)
    assert state["bound_prompt_passage_count"] == len(passages)
    assert "lottery_handbook_deep_notes.md" in state["bound_prompt_docs"]
    assert registration["metadata"]["bound_prompt_passage_count"] == len(passages)


def test_service_prefers_letta_client_in_explicit_no_mcp_mode(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LOTTERY_WORLD_NO_MCP_BACKEND", "auto")
    fake_client = NoMcpFakeLettaClient()
    monkeypatch.setattr("app.services.lottery.research_service.LettaNoMcpClient", lambda: fake_client)

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = _workspace()
        graph_service = FakeGraphService()
        kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
        world_runtime = LotteryWorldRuntime(
            graph_service,
            store=WorldSessionStore(str(Path(temp_dir) / "world")),
            letta_client=None,
            kuzu_graph_service=kuzu_graph_service,
        )
        service = LotteryResearchService(
            repository=WorkspaceRepository(workspace),
            graph_service=graph_service,
            kuzu_graph_service=kuzu_graph_service,
            report_writer=LotteryReportWriter(Path(temp_dir)),
            world_runtime=world_runtime,
        )

    assert service.world_v2_runtime.letta_client is fake_client


def test_service_can_force_local_client_in_explicit_no_mcp_mode(monkeypatch):
    monkeypatch.setenv("LOTTERY_WORLD_ALLOW_NO_MCP", "true")
    monkeypatch.setenv("LOTTERY_WORLD_NO_MCP_BACKEND", "local")
    monkeypatch.setenv("LETTA_BASE_URL", "http://127.0.0.1:8283/v1")

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = _workspace()
        graph_service = FakeGraphService()
        kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
        world_runtime = LotteryWorldRuntime(
            graph_service,
            store=WorldSessionStore(str(Path(temp_dir) / "world")),
            letta_client=None,
            kuzu_graph_service=kuzu_graph_service,
        )
        service = LotteryResearchService(
            repository=WorkspaceRepository(workspace),
            graph_service=graph_service,
            kuzu_graph_service=kuzu_graph_service,
            report_writer=LotteryReportWriter(Path(temp_dir)),
            world_runtime=world_runtime,
        )

    assert isinstance(service.world_v2_runtime.letta_client, LocalWorldClient)


def test_world_market_runtime_removes_bettor_personas():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir, DuplicateBettorLettaClient())
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session = service.get_world_session(result["world_session"]["session_id"])

    assert result["world_session"]["status"] == "await_result"
    assert result["pending_prediction"]["purchase_recommendation"]["status"] == "ready"
    assert not any(item["code"] == "bettor_plan_invalid" for item in result["execution_log"])
    assert not any(
        item["session_agent_id"].startswith("bettor_")
        for item in session["session"]["agents"]
    )


def test_world_persists_execution_log_for_successful_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        session_id = result["world_session"]["session_id"]
        session = service.get_world_session(session_id)

    logs = session["session"]["execution_log"]
    assert logs
    assert any(item["code"] == "session_created" for item in logs)
    assert any(item["code"] == "prediction_cycle_start" for item in logs)
    assert any(item["code"] == "mcp_tooling_ready" for item in logs)


def test_world_failure_persists_structured_mcp_execution_log():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir, UnsupportedStdioLettaClient())
        with pytest.raises(RuntimeError, match="stdio is not supported"):
            service.advance_world_session(
                pick_size=5,
                strategy_ids=["cold_rule", "hot_rule"],
                issue_parallelism=1,
                agent_dialogue_enabled=False,
                live_interview_enabled=False,
            )
        session_id = service.get_current_world_session()["session"]["session_id"]
        session = service.get_world_session(session_id)

    error = session["session"]["error"]
    logs = session["session"]["execution_log"]
    assert error["code"] == "mcp_stdio_unsupported"
    assert "当前 Letta 环境不支持 stdio MCP" in error["message"]
    assert any("LETTA_BASE_URL=" in line for line in error["details"])
    assert any(item["code"] == "mcp_server_prepare_failed" for item in logs)
    assert any(item["code"] == "mcp_stdio_unsupported" for item in logs)


def test_world_failure_can_resume_same_target_from_failed_phase():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir, BrokenPurchaseLettaClient())
        with pytest.raises(ValueError, match="purchase_chair returned .*plan"):
            service.advance_world_session(
                pick_size=5,
                strategy_ids=["cold_rule", "hot_rule"],
                issue_parallelism=1,
                agent_dialogue_enabled=False,
                live_interview_enabled=True,
            )
        session_id = service.get_current_world_session()["session"]["session_id"]
        failed = service.get_world_session(session_id)
        assert failed["session"]["status"] == "failed"
        assert failed["session"]["failed_phase"] == "plan_synthesis"
        assert failed["session"]["error"]["code"] == "purchase_plan_invalid"
        service.world_v2_runtime.letta_client = FakeLettaClient()
        service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
        resumed = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
            session_id=session_id,
        )

    assert resumed["world_session"]["status"] == "await_result"
    assert resumed["world_session"]["failed_phase"] is None
    assert resumed["pending_prediction"]["purchase_recommendation"]["status"] == "ready"


def test_world_repairs_purchase_chair_plan_after_budget_validation_failure():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir, RepairingPurchaseLettaClient())
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )

    logs = result["execution_log"]
    plan = result["pending_prediction"]["purchase_recommendation"]
    assert result["world_session"]["status"] == "await_result"
    assert plan["status"] == "ready"
    assert plan["ticket_count"] <= 25
    assert any(item["code"] == "purchase_plan_invalid_attempt" for item in logs)
    assert any(item["code"] == "purchase_plan_repaired" for item in logs)


def test_world_advance_settles_previous_round_then_moves_to_new_pending_issue():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir)
        first = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )
        session_id = first["world_session"]["session_id"]
        next_workspace = replace(
            workspace,
            pending_draws=(_draw("2026010", ()),),
            completed_draws=tuple([*workspace.completed_draws, _draw("2026009", (1, 2, 3, 40, 41))]),
        )
        service.runtime.load_workspace = lambda: next_workspace  # type: ignore[method-assign]
        second = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
            session_id=session_id,
        )
        session = service.get_world_session(session_id)

    assert second["world_session"]["status"] == "await_result"
    assert second["pending_prediction"]["period"] == "2026010"
    assert session["session"]["settlement_history"][-1]["period"] == "2026009"
    assert session["session"]["settlement_history"][-1]["reference_plan_profit"] is not None
    assert session["session"]["current_round"]["target_period"] == "2026010"


def test_world_visible_through_period_controls_prediction_progression():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        targeted = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            visible_through_period="2026007",
        )
        progressed = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            session_id=targeted["world_session"]["session_id"],
            visible_through_period="2026008",
        )

    assert targeted["pending_prediction"]["visible_through_period"] == "2026007"
    assert targeted["pending_prediction"]["period"] == "2026008"
    assert progressed["pending_prediction"]["visible_through_period"] == "2026008"
    assert progressed["pending_prediction"]["period"] == "2026009"
    assert progressed["world_session"]["latest_review"]["period"] == "2026008"


def test_kuzu_runtime_projection_tracks_issue_signal_plan_and_trust():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )
        projection = service.kuzu_graph_service.runtime_projection()
        influencers = service.kuzu_graph_service.top_influencers(3)
        crowding = service.kuzu_graph_service.market_crowding([1, 2, 3, 4, 5])

    assert projection["issue"]["id"] == "draw:2026009"
    assert any(item["strategy_id"] == "cold_rule" for item in projection["signals"])
    assert any(item["persona_id"] == "purchase_chair" for item in projection["bet_plans"])
    assert any(edge["target_id"] == "cold_rule" for edge in projection["trust_edges"])
    assert influencers[0]["agent_id"] == "cold_rule"
    assert crowding > 0


def test_world_requires_at_least_one_pending_draw():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir)
        invalid_workspace = replace(workspace, pending_draws=())
        service.runtime.load_workspace = lambda: invalid_workspace  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="at least one pending draw"):
            service.advance_world_session(
                pick_size=5,
                strategy_ids=["cold_rule", "hot_rule"],
                issue_parallelism=1,
                agent_dialogue_enabled=False,
                live_interview_enabled=True,
            )


def test_world_support_exposes_prompt_and_report_passages():
    long_text = "Cold-number note.\n" * 900
    context = type(
        "Context",
        (),
        {
            "knowledge_documents": (
                KnowledgeDocument("basis.md", "knowledge", "knowledge/learn/basis.md", len(long_text), long_text, ("cold",)),
                KnowledgeDocument("prediction_report.md", "report", "reports/prediction_report.md", len(long_text), long_text, ("cold",)),
            ),
            "prompt_documents": (
                KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", len(long_text), long_text, ("cold",)),
            ),
        },
    )()

    prompt_chunks = prompt_passages(context)
    report_chunks = report_passages(context)

    assert len(prompt_chunks) == 1
    assert len(report_chunks) == 1
    assert prompt_chunks[0].startswith("Source: prompt.md")
    assert report_chunks[0].startswith("Source: prediction_report.md")


def test_world_support_extracts_first_complete_json_object():
    payload = parse_json_response('Result:\n{"numbers":[1,2,3,4,5],"comment":"ok"}\nextra {"ignore":true}')

    assert payload["numbers"] == [1, 2, 3, 4, 5]
    assert payload["comment"] == "ok"


def _service(temp_dir: str, fake_client=None):
    workspace = _workspace()
    graph_service = FakeGraphService()
    kuzu_graph_service = KuzuGraphService(db_root=str(Path(temp_dir) / "kuzu"))
    world_runtime = LotteryWorldRuntime(
        graph_service,
        store=WorldSessionStore(str(Path(temp_dir) / "world")),
        letta_client=fake_client or FakeLettaClient(),
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
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 40, "Use the market synthesis prediction format.", ("prompt",)),
        KnowledgeDocument(
            "lottery_handbook_deep_notes.md",
            "prompt",
            "knowledge/prompts/lottery_handbook_deep_notes.md",
            120,
            "Handbook doctrine: avoid crowding, reduce shared-prize dilution, and distrust public-looking number shapes.",
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
        KnowledgeDocument(
            "prediction_report.md",
            "report",
            "reports/prediction_report.md",
            80,
            "Backtest says cold numbers remain stable and high ROI.",
            ("cold", "ROI"),
            {"created_at": "2026-03-15T08:00:00", "effective_period": "2026008", "max_visible_period": "2026009"},
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
        daily_energy=EnergySignature("甲", "子", ("天机",)),
        hourly_energy=EnergySignature("乙", "丑", ("太阴",)),
    )
