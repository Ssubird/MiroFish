from pathlib import Path
import sys
import tempfile
import time

from app.services.lottery.world_jobs import WorldRunManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lottery_world_runtime import _service


def test_world_evolution_accepts_missing_empty_and_none_target_period():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        missing = service.run_world_evolution(
            iterations=1,
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
        )
        explicit_empty = service.run_world_evolution(
            iterations=1,
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            target_period="",
        )
        explicit_none = service.run_world_evolution(
            iterations=1,
            pick_size=5,
            strategy_ids=["cold_rule", "hot_rule"],
            issue_parallelism=1,
            agent_dialogue_enabled=False,
            live_interview_enabled=False,
            target_period=None,
        )

    assert missing["final_state"]["pending_prediction"]["period"] == "2026008"
    assert explicit_empty["final_state"]["pending_prediction"]["period"] == "2026008"
    assert explicit_none["final_state"]["pending_prediction"]["period"] == "2026008"


def test_world_run_manager_returns_queued_session_before_background_execution():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        manager = WorldRunManager(max_workers=1)
        try:
            initial = manager.start(
                service,
                ["cold_rule", "hot_rule"],
                {
                    "pick_size": 5,
                    "issue_parallelism": 1,
                    "agent_dialogue_enabled": False,
                    "live_interview_enabled": False,
                    "runtime_mode": "world_v2_market",
                },
            )
            session_id = initial["world_session"]["session_id"]
            final = _wait_for_status(service, session_id, {"await_result"})
        finally:
            manager._executor.shutdown(wait=True)

    assert initial["world_session"]["status"] == "queued"
    assert initial["world_session"]["current_phase"] == "queued"
    assert final["status"] == "await_result"


def test_world_run_manager_persists_failed_session_for_early_evolution_errors():
    with tempfile.TemporaryDirectory() as temp_dir:
        service, _, _ = _service(temp_dir)
        manager = WorldRunManager(max_workers=1)

        def boom(*args, **kwargs):
            raise RuntimeError("early async boom")

        service.run_world_evolution = boom  # type: ignore[method-assign]
        try:
            initial = manager.start_evolution(
                service,
                ["cold_rule", "hot_rule"],
                {
                    "pick_size": 5,
                    "issue_parallelism": 1,
                    "agent_dialogue_enabled": False,
                    "live_interview_enabled": False,
                    "runtime_mode": "world_v2_market",
                },
                iterations=1,
            )
            session_id = initial["world_session"]["session_id"]
            failed = _wait_for_status(service, session_id, {"failed"})
            timeline = service.get_world_timeline(session_id, 0, 20, latest=True)
        finally:
            manager._executor.shutdown(wait=True)

    assert initial["world_session"]["status"] == "queued"
    assert failed["error"]["message"] == "early async boom"
    assert failed["failed_phase"] == "queued"
    assert any(
        item["event_type"] == "run_failed" and "early async boom" in item["content"]
        for item in timeline["items"]
    )


def _wait_for_status(service, session_id: str, expected: set[str], timeout_seconds: float = 5.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        session = service.get_world_session(session_id)["session"]
        if session["status"] in expected:
            return session
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {expected}; last session={service.get_world_session(session_id)['session']}")
