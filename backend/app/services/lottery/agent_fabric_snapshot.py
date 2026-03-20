"""Agent fabric export and snapshot helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent_fabric_registry import AgentFabricRegistry
from .catalog import build_strategy_catalog
from .paths import AGENT_FABRIC_GENERATED_DIR, lottery_relative_path
from .serializers import serialize_strategy


SNAPSHOT_BASENAME = "agent_fabric_snapshot"


def write_agent_fabric_snapshot(
    registry: AgentFabricRegistry,
    assets,
    execution_registry,
    generated_root: Path | None = None,
) -> dict[str, Any]:
    payload = build_agent_fabric_export(registry, assets, execution_registry)
    root = generated_root or AGENT_FABRIC_GENERATED_DIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{SNAPSHOT_BASENAME}.json"
    markdown_path = root / f"{SNAPSHOT_BASENAME}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_snapshot_markdown(payload), encoding="utf-8")
    return {
        "json_path": _display_path(json_path),
        "markdown_path": _display_path(markdown_path),
        "payload": payload,
    }


def build_agent_fabric_export(registry: AgentFabricRegistry, assets, execution_registry) -> dict[str, Any]:
    registry.validate_assets(assets)
    resolved = [registry.resolved_agent(agent_id) for agent_id in sorted(registry.agents())]
    docs = assets.knowledge_documents
    strategy_catalog = build_strategy_catalog(chart_count=len(assets.chart_profiles))
    data_inventory = [serialize_strategy(strategy) for strategy in assets.strategies.values()]
    python_only = [
        serialize_strategy(strategy)
        for strategy in strategy_catalog.values()
        if getattr(strategy, "group", "") in {"data", "metaphysics", "hybrid", "full_context"}
    ]
    rows = []
    for spec in resolved:
        bundle = registry.prompt_assets(spec.agent_id, docs, {})
        rows.append(
            {
                **spec.to_dict(),
                "resolved_execution_binding": execution_registry.resolve_binding(
                    spec.agent_id,
                    spec.role_kind,
                    spec.group,
                    registry.execution_overrides(),
                    routing_mode="metadata_only",
                ).to_dict(),
                "prompt_sources": list(bundle.sources),
                "bound_documents": list(bundle.document_names),
                "prompt_passage_count": len(bundle.passages),
            }
        )
    return {
        "phases": [item.to_dict() for item in registry.phases().values()],
        "groups": [item.to_dict() for item in registry.groups().values()],
        "agents": rows,
        "execution_overrides": registry.execution_overrides(),
        "execution_catalog_summary": execution_registry.export_catalog(),
        "data_inventory": data_inventory,
        "python_catalog_inventory": python_only,
        "mount_points": {
            "strategy_catalog": "backend/app/services/lottery/catalog.py::build_strategy_catalog",
            "market_catalog": "backend/app/services/lottery/catalog.py::build_market_v2_catalog",
        },
    }


def _snapshot_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Agent Fabric Snapshot",
        "",
        "## Single Agent Input Sources",
        "",
        "| Agent | Role | Group | Profile | Phases | Shared Blocks | Bound Documents |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload.get("agents", []):
        binding = dict(item.get("resolved_execution_binding") or {})
        lines.append(
            f"| {item.get('agent_id', '-')} | {item.get('role_kind', '-')} | {item.get('group', '-')} | "
            f"{binding.get('profile_id', '-')} | {', '.join(item.get('phases', [])) or '-'} | "
            f"{', '.join(item.get('shared_memory_keys', [])) or '-'} | {', '.join(item.get('bound_documents', [])) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Phase Group Agent Matrix",
            "",
            "| Phase | Active Groups | Agent IDs |",
            "| --- | --- | --- |",
        ]
    )
    for phase in payload.get("phases", []):
        phase_id = str(phase.get("phase_id", "-"))
        agent_ids = [item.get("agent_id", "-") for item in payload.get("agents", []) if phase_id in item.get("phases", [])]
        lines.append(
            f"| {phase_id} | {', '.join(phase.get('active_groups', [])) or '-'} | {', '.join(agent_ids) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Data Group Inventory",
            "",
            "| Strategy | Group | Kind | Required History |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in payload.get("python_catalog_inventory", []):
        lines.append(
            f"| {item.get('strategy_id', '-')} | {item.get('group', '-')} | {item.get('kind', '-')} | {item.get('required_history', '-')} |"
        )
    return "\n".join(lines).strip() + "\n"


def _display_path(path: Path) -> str:
    try:
        return lottery_relative_path(path)
    except ValueError:
        return str(path)
