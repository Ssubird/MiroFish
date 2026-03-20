from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app import create_app
from app.config import Config
from app.services.lottery.agent_fabric_registry import AgentFabricConfigError, AgentFabricRegistry
from app.services.lottery.execution_registry import ExecutionRegistry
from app.services.lottery.models import GraphSnapshot, KnowledgeDocument
from app.services.lottery.research_types import WorkspaceAssets


def test_agent_fabric_rejects_duplicate_agent_ids(tmp_path):
    root = _write_fabric_root(tmp_path)
    duplicate = _agent_payload()
    (root / "agents" / "duplicate.yaml").write_text(
        yaml.safe_dump(duplicate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(AgentFabricConfigError, match="Duplicate agent_id"):
        _registry(root, tmp_path)


def test_agent_fabric_rejects_unknown_phase_and_profile(tmp_path):
    payload = _agent_payload(phases=["missing_phase"], profile_id="ghost_profile")
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})

    with pytest.raises(AgentFabricConfigError, match="unknown phase|unknown profile_id"):
        _registry(root, tmp_path)


def test_agent_fabric_rejects_unknown_block_and_invalid_dialogue_mode(tmp_path):
    payload = _agent_payload(
        prompt={"blocks": [{"type": "runtime_text", "name": "ghost_block"}]},
        dialogue_policy={"mode": "loop_forever"},
    )
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})

    with pytest.raises(AgentFabricConfigError, match="Unknown runtime_text block|Unsupported dialogue_policy.mode"):
        _registry(root, tmp_path)


def test_agent_fabric_rejects_missing_workspace_file(tmp_path, monkeypatch):
    workspace_root = tmp_path / "ziweidoushu"
    monkeypatch.setattr(Config, "LOTTERY_DATA_ROOT", str(workspace_root), raising=False)
    payload = _agent_payload(
        prompt={"blocks": [{"type": "workspace_file", "path": "data/draws/keno8_predict_data.json"}]},
    )
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})

    with pytest.raises(AgentFabricConfigError, match="Unknown workspace file"):
        _registry(root, tmp_path)


def test_agent_fabric_validate_assets_rejects_missing_document_reference(tmp_path):
    payload = _agent_payload(document_refs=["missing.md"])
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})
    registry = _registry(root, tmp_path)

    with pytest.raises(AgentFabricConfigError, match="Unknown workspace document reference"):
        registry.validate_assets(_assets())


def test_agent_fabric_validate_assets_rejects_unknown_visible_agent(tmp_path):
    payload = _agent_payload(visible_agents=["ghost_agent"])
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})
    registry = _registry(root, tmp_path)

    with pytest.raises(AgentFabricConfigError, match="unknown visible agent"):
        registry.validate_assets(_assets())


def test_agent_fabric_prompt_assets_include_workspace_file_chunks(tmp_path, monkeypatch):
    workspace_root = tmp_path / "ziweidoushu"
    draw_file = workspace_root / "data" / "draws" / "keno8_predict_data.json"
    draw_file.parent.mkdir(parents=True, exist_ok=True)
    draw_file.write_text('[{"period":"2026001","numbers":[1,2,3,4,5]}]', encoding="utf-8")
    monkeypatch.setattr(Config, "LOTTERY_DATA_ROOT", str(workspace_root), raising=False)
    payload = _agent_payload(
        prompt={
            "blocks": [
                {"type": "workspace_document", "name": "prompt.md"},
                {"type": "workspace_file", "path": "data/draws/keno8_predict_data.json"},
            ]
        },
        document_refs=[],
    )
    root = _write_fabric_root(tmp_path, agents={"social_consensus_feed.yaml": payload})
    registry = _registry(root, tmp_path)

    bundle = registry.prompt_assets("social_consensus_feed", _assets().knowledge_documents, {})

    assert "prompt.md" in bundle.document_names
    assert "data/draws/keno8_predict_data.json" in bundle.document_names
    assert any(item["source_type"] == "workspace_file" for item in bundle.sources)
    assert any("2026001" in passage for passage in bundle.passages)
    assert any('"numbers":[1,2,3,4,5]' in passage for passage in bundle.passages)


def test_agent_fabric_registry_route_exports_snapshot(tmp_path, monkeypatch):
    generated_root = tmp_path / "generated"
    monkeypatch.setattr(Config, "AGENT_FABRIC_GENERATED_ROOT", str(generated_root), raising=False)
    monkeypatch.setattr(
        "app.services.lottery.agent_fabric_snapshot.AGENT_FABRIC_GENERATED_DIR",
        generated_root,
    )

    app = create_app()
    client = app.test_client()
    response = client.get("/api/lottery/agent-fabric/registry")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "agents" in payload["data"]["registry"]
    assert Path(generated_root / "agent_fabric_snapshot.json").is_file()


def _write_fabric_root(
    tmp_path: Path,
    *,
    agents: dict[str, dict] | None = None,
) -> Path:
    root = tmp_path / "agent_fabric"
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "phases": [{"phase_id": "social_propagation", "active_groups": ["social"]}],
        "groups": [{"group_id": "social", "role_kind": "social", "default_profile_id": "social_default"}],
    }
    (root / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (root / "prompts" / "social.md").write_text("social doctrine", encoding="utf-8")
    rows = agents or {"social_consensus_feed.yaml": _agent_payload()}
    for name, payload in rows.items():
        (root / "agents" / name).write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return root


def _agent_payload(**overrides) -> dict:
    payload = {
        "agent_id": "social_consensus_feed",
        "display_name": "LLM-social",
        "description": "social role",
        "behavior_template": "social_discussion",
        "role_kind": "social",
        "group": "social",
        "phases": ["social_propagation"],
        "profile_id": "social_default",
        "prompt": {"blocks": [{"type": "prompt_file", "path": "social.md"}]},
        "document_refs": ["prompt.md"],
        "shared_memory_keys": ["current_issue"],
        "visible_groups": ["data", "social"],
        "visible_agents": [],
        "dialogue_policy": {"mode": "rounds", "rounds": 2},
        "limits": {"max_prompt_passages": 10},
    }
    payload.update(overrides)
    return payload


def _registry(root: Path, tmp_path: Path) -> AgentFabricRegistry:
    return AgentFabricRegistry(
        root=root,
        execution_registry=ExecutionRegistry(config_path=_execution_config(tmp_path)),
    )


def _execution_config(tmp_path: Path) -> Path:
    path = tmp_path / "execution_config.yaml"
    path.write_text(
        "\n".join(
            [
                "providers: []",
                "models: []",
                "profiles:",
                "  - profile_id: default",
                "    provider_id: default",
                "    model_id: default",
                "  - profile_id: social_default",
                "    provider_id: default",
                "    model_id: default",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _assets() -> WorkspaceAssets:
    docs = (
        KnowledgeDocument("prompt.md", "prompt", "knowledge/prompts/prompt.md", 12, "prompt body", ("prompt",)),
        KnowledgeDocument("handbook.md", "knowledge", "knowledge/learn/handbook.md", 12, "handbook", ("handbook",)),
    )
    strategies = {"cold_rule": SimpleNamespace(strategy_id="cold_rule", group="data")}
    return WorkspaceAssets(
        completed_draws=(),
        pending_draws=(),
        knowledge_documents=docs,
        chart_profiles=(),
        strategies=strategies,
        local_workspace_graph=GraphSnapshot("workspace", 0, 0, (), {}, (), 0, ()),
        kuzu_graph_status={},
        zep_graph_status={},
    )
