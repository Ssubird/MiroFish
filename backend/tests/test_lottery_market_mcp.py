import json
import os
import tempfile
from pathlib import Path

from app.services.lottery.mcp_servers import happy8_rules_mcp, kuzu_market_mcp, report_memory_mcp, world_state_mcp
from app.services.lottery.mcp_servers import support as mcp_support
from app.services.lottery.world_runtime import LotteryWorldRuntime

from app.services.lottery.kuzu_graph import KuzuGraphService
from app.services.lottery.report_writer import LotteryReportWriter
from app.services.lottery.research_service import LotteryResearchService
from app.services.lottery.world_store import WorldSessionStore

from test_lottery_world_runtime import FakeGraphService, FakeLettaClient, WorkspaceRepository, _workspace


def test_market_mcp_servers_use_real_session_context(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = _workspace()
        kuzu_graph_service = KuzuGraphService(db_root=os.path.join(temp_dir, "kuzu"))
        service = LotteryResearchService(
            repository=WorkspaceRepository(workspace),
            graph_service=FakeGraphService(),
            kuzu_graph_service=kuzu_graph_service,
            report_writer=LotteryReportWriter(Path(temp_dir)),
            world_runtime=LotteryWorldRuntime(
                FakeGraphService(),
                store=WorldSessionStore(os.path.join(temp_dir, "world")),
                letta_client=FakeLettaClient(),
                kuzu_graph_service=kuzu_graph_service,
            ),
        )
        service.runtime.load_workspace = lambda: workspace  # type: ignore[method-assign]
        result = service.advance_world_session(
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=True,
        )
        session_id = result["world_session"]["session_id"]
        plan_json = json.dumps(result["pending_prediction"]["purchase_plan"], ensure_ascii=False)

        monkeypatch.setenv("LOTTERY_WORLD_SESSION_ID", session_id)
        monkeypatch.setenv("LOTTERY_WORLD_STATE_ROOT", os.path.join(temp_dir, "world"))
        monkeypatch.setenv("KUZU_GRAPH_ROOT", os.path.join(temp_dir, "kuzu"))
        monkeypatch.setenv("LOTTERY_DATA_ROOT", temp_dir)
        mcp_support.world_store.cache_clear()
        mcp_support.kuzu_service.cache_clear()

        assert happy8_rules_mcp.validate_plan(plan_json) is True
        assert happy8_rules_mcp.price_plan(plan_json) == result["pending_prediction"]["purchase_plan"]["total_cost_yuan"]

        snapshot = world_state_mcp.get_market_snapshot()
        assert snapshot["issue"]["period"] == "2026009"
        assert snapshot["feed_events"] > 0

        digest = report_memory_mcp.report_digest("2026009")
        assert "Backtest says cold numbers remain stable" in digest

        results = kuzu_market_mcp.search_docs("cold", limit=3)
        influencers = kuzu_market_mcp.top_influencers(limit=3)
        assert results
        assert influencers[0]["agent_id"] == "cold_rule"
