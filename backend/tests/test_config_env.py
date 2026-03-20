import os

from app.config import reload_project_env


def test_reload_project_env_keeps_existing_process_env(monkeypatch):
    monkeypatch.setenv("LETTA_BASE_URL", "http://override.test/v1")

    reload_project_env()

    assert os.environ["LETTA_BASE_URL"] == "http://override.test/v1"
