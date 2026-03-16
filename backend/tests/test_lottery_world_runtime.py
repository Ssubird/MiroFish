from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from app.services.lottery.agents.base import StrategyAgent
from app.services.lottery.models import DrawRecord, EnergySignature, GraphSnapshot, KnowledgeDocument, StrategyPrediction
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.research_types import WorkspaceAssets
from app.services.lottery.world_runtime import LotteryWorldRuntime
from app.services.lottery.world_store import WorldSessionStore
from app.services.lottery.world_support import parse_json_response, prompt_passages, report_passages


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
    def __init__(self):
        self.blocks = {}
        self.passages = {}

    def create_agent(self, name, description, memory_blocks, metadata=None):
        agent_id = f"letta_{name}"
        self.blocks[agent_id] = dict(memory_blocks)
        self.passages[agent_id] = []
        return agent_id

    def update_block(self, agent_id, block_label, value):
        self.blocks.setdefault(agent_id, {})[block_label] = value

    def add_passage(self, agent_id, text, tags=None):
        self.passages.setdefault(agent_id, []).append({"text": text, "tags": tags or []})

    def send_message(self, agent_id, content):
        if "External interview question" in content:
            return "Cold Rule currently stays with [1, 2, 3, 4, 5]."
        if "purchase_chair" in agent_id:
            return (
                '{"plan_style":"balanced","plan_type":"wheel","play_size":5,'
                '"play_size_review":{"3":"too thin","4":"acceptable","5":"best balance","6":"too diffuse"},'
                '"chosen_edge":"balanced coverage on the strongest five plus one hedge",'
                '"trusted_strategy_ids":["cold_rule"],"wheel_numbers":[1,2,3,4,5,6],'
                '"primary_ticket":[1,2,3,4,5],"core_numbers":[1,2,3],"hedge_numbers":[6],'
                '"avoid_numbers":[10],"comment":"chair closes on balanced wheel",'
                '"rationale":"chair closes on balanced wheel"}'
            )
        if "budget_guard" in agent_id:
            return self._purchase_response("tickets", [1, 2, 3, 4, 5], [], [], "guard prefers concentration", content)
        if "coverage_builder" in agent_id:
            return self._purchase_response("wheel", [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6], [], "coverage adds one hedge", content)
        if "upside_hunter" in agent_id:
            return self._purchase_response("dan_tuo", [1, 2, 3, 4, 5], [], [1, 2], "upside pushes dan_tuo", content)
        if "Reply publicly" in content:
            return '{"numbers":[1,2,3,4,5],"comment":"stay with cold cluster","support_agent_ids":["cold_rule"],"rationale":"debate keeps cold"}'
        return '{"comment":"postmortem note","focus":["cold"],"trusted_strategy_ids":["cold_rule"]}'

    def _purchase_response(self, plan_type, primary_ticket, wheel_numbers, banker_numbers, note, content):
        support = '["budget_guard"]' if "Committee discussion so far" in content else "[]"
        drag = "[3,4,5,6]" if plan_type == "dan_tuo" else "[]"
        wheel = str(wheel_numbers) if wheel_numbers else "[]"
        bankers = str(banker_numbers) if banker_numbers else "[]"
        return (
            "{"
            f'"plan_style":"committee","plan_type":"{plan_type}","play_size":5,'
            '"play_size_review":{"3":"too defensive","4":"still light","5":"fits main consensus","6":"too loose"},'
            f'"chosen_edge":"{note}",'
            f'"trusted_strategy_ids":["cold_rule"],"tickets":[{primary_ticket}],"wheel_numbers":{wheel},'
            f'"banker_numbers":{bankers},"drag_numbers":{drag},"primary_ticket":{primary_ticket},'
            f'"core_numbers":[1,2,3],"hedge_numbers":[6],"avoid_numbers":[10],'
            f'"support_role_ids":{support},"comment":"{note}","rationale":"{note}"'
            "}"
        )


class BrokenPurchaseLettaClient(FakeLettaClient):
    def send_message(self, agent_id, content):
        if "purchase_chair" in agent_id:
            return '{"plan_style":"broken","primary_ticket":[1,2,3,4,5],"rationale":"missing plan_type"}'
        return super().send_message(agent_id, content)


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


def test_world_advance_creates_persistent_session_and_asset_manifest():
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

    assert result["evaluation"]["runtime_mode"] == "world_v1"
    assert result["evaluation"]["world_mode"] == "persistent"
    assert result["evaluation"]["budget_yuan"] == 50
    assert result["evaluation"]["target_period"] == "2026009"
    assert result["world_session"]["status"] == "await_result"
    assert result["pending_prediction"]["period"] == "2026009"
    assert len(result["pending_prediction"]["ensemble_numbers"]) == 5
    assert len(result["pending_prediction"]["alternate_numbers"]) == 3
    assert any(item["event_type"] == "debate_summary" for item in result["pending_prediction"]["world_timeline_preview"])
    assert result["pending_prediction"]["purchase_plan"]["play_size_review"]["5"] == "best balance"
    roles = {item["role"] for item in result["world_session"]["asset_manifest"]}
    assert roles == {"authoritative_data", "active_prompt", "manual_reference_only"}
    assert result["world_session"]["manual_reference_documents"][0]["name"] == "prediction_report.md"
    assert "prediction_report" in result["world_session"]["shared_memory"]["report_digest"]
    assert "letta_world_judge" not in fake_client.blocks
    assert "letta_rule_interpreter" not in fake_client.blocks
    assert session["session"]["latest_purchase_plan"]["ticket_count"] >= 1


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
        assert failed["session"]["failed_phase"] == "purchase_committee"
        service.world_runtime.letta_client = FakeLettaClient()
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
    assert resumed["pending_prediction"]["purchase_plan"]["status"] == "ready"


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
    assert session["session"]["settlement_history"][-1]["consensus_hits"] >= 0
    assert session["session"]["current_round"]["target_period"] == "2026010"


def test_world_requires_exactly_one_pending_draw():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, workspace = _service(temp_dir)
        invalid_workspace = replace(workspace, pending_draws=())
        service.runtime.load_workspace = lambda: invalid_workspace  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="exactly one pending draw"):
            service.advance_world_session(
                pick_size=5,
                strategy_ids=["cold_rule", "hot_rule"],
                issue_parallelism=1,
                agent_dialogue_enabled=False,
                live_interview_enabled=True,
            )


def test_world_support_uses_compact_prompt_passages_only_for_letta_memory():
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
    assert report_chunks == []
    assert prompt_chunks[0].startswith("Source: prompt.md")


def test_world_support_extracts_first_complete_json_object():
    payload = parse_json_response('Result:\n{"numbers":[1,2,3,4,5],"comment":"ok"}\nextra {"ignore":true}')

    assert payload["numbers"] == [1, 2, 3, 4, 5]
    assert payload["comment"] == "ok"


def _service(temp_dir: str, fake_client=None):
    workspace = _workspace()
    graph_service = FakeGraphService()
    world_runtime = LotteryWorldRuntime(
        graph_service,
        store=WorldSessionStore(str(Path(temp_dir) / "world")),
        letta_client=fake_client or FakeLettaClient(),
    )
    service = LotteryResearchService(
        repository=WorkspaceRepository(workspace),
        graph_service=graph_service,
        report_writer=LotteryReportWriter(Path(temp_dir)),
        world_runtime=world_runtime,
    )
    service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
    return service, world_runtime.letta_client, workspace


def _workspace() -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 40, "Use the fixed 5+3 prediction format.", ("prompt",)),
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
