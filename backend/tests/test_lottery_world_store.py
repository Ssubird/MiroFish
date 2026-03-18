from pathlib import Path
import tempfile

import pytest

from app.services.lottery.world_execution_log import build_error_payload
from app.services.lottery.world_models import WorldSession
from app.services.lottery.world_store import WorldSessionStore


def test_world_store_retries_session_replace_on_windows_style_permission_error(monkeypatch):
    attempts = {"count": 0}
    original_replace = Path.replace

    def flaky_replace(self, target):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise PermissionError("[WinError 5] access denied")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with tempfile.TemporaryDirectory() as temp_dir:
        store = WorldSessionStore(str(Path(temp_dir) / "world"))
        session = WorldSession.create("world_v2_market", 5, 50, ["cold_50"], "goal")
        store.save_session(session)
        saved = store.load_session(session.session_id)

    assert attempts["count"] == 3
    assert saved["session_id"] == session.session_id


def test_world_store_cleans_tmp_file_after_persistent_replace_failure(monkeypatch):
    def blocked_replace(self, target):
        raise PermissionError("[WinError 5] access denied")

    monkeypatch.setattr(Path, "replace", blocked_replace)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "world"
        store = WorldSessionStore(str(root))
        session = WorldSession.create("world_v2_market", 5, 50, ["cold_50"], "goal")
        with pytest.raises(PermissionError, match="WinError 5"):
            store.save_session(session)
        tmp_files = list((root / session.session_id).glob("session.json.*.tmp"))

    assert tmp_files == []


def test_build_error_payload_classifies_windows_state_file_lock():
    error = build_error_payload(
        PermissionError(
            "[WinError 5] 拒绝访问。: 'E:\\\\MoFish\\\\MiroFish\\\\ziweidoushu\\\\.world_state\\\\world_x\\\\session.json.tmp' -> "
            "'E:\\\\MoFish\\\\MiroFish\\\\ziweidoushu\\\\.world_state\\\\world_x\\\\session.json'"
        ),
        phase="queued",
        period="2026061",
    )

    assert error["code"] == "world_state_write_locked"
