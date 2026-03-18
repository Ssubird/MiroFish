"""业务服务模块导出。

保持顶层包可导入，但避免在导入 `app.services` 时立刻拉起旧的
Zep/仿真链路依赖，防止无关模块拖慢彩票运行时或让可选依赖变成隐性必需。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "OntologyGenerator": (".ontology_generator", "OntologyGenerator"),
    "GraphBuilderService": (".graph_builder", "GraphBuilderService"),
    "TextProcessor": (".text_processor", "TextProcessor"),
    "ZepEntityReader": (".zep_entity_reader", "ZepEntityReader"),
    "EntityNode": (".zep_entity_reader", "EntityNode"),
    "FilteredEntities": (".zep_entity_reader", "FilteredEntities"),
    "OasisProfileGenerator": (".oasis_profile_generator", "OasisProfileGenerator"),
    "OasisAgentProfile": (".oasis_profile_generator", "OasisAgentProfile"),
    "SimulationManager": (".simulation_manager", "SimulationManager"),
    "SimulationState": (".simulation_manager", "SimulationState"),
    "SimulationStatus": (".simulation_manager", "SimulationStatus"),
    "SimulationConfigGenerator": (
        ".simulation_config_generator",
        "SimulationConfigGenerator",
    ),
    "SimulationParameters": (".simulation_config_generator", "SimulationParameters"),
    "AgentActivityConfig": (".simulation_config_generator", "AgentActivityConfig"),
    "TimeSimulationConfig": (".simulation_config_generator", "TimeSimulationConfig"),
    "EventConfig": (".simulation_config_generator", "EventConfig"),
    "PlatformConfig": (".simulation_config_generator", "PlatformConfig"),
    "SimulationRunner": (".simulation_runner", "SimulationRunner"),
    "SimulationRunState": (".simulation_runner", "SimulationRunState"),
    "RunnerStatus": (".simulation_runner", "RunnerStatus"),
    "AgentAction": (".simulation_runner", "AgentAction"),
    "RoundSummary": (".simulation_runner", "RoundSummary"),
    "ZepGraphMemoryUpdater": (
        ".zep_graph_memory_updater",
        "ZepGraphMemoryUpdater",
    ),
    "ZepGraphMemoryManager": (
        ".zep_graph_memory_updater",
        "ZepGraphMemoryManager",
    ),
    "AgentActivity": (".zep_graph_memory_updater", "AgentActivity"),
    "SimulationIPCClient": (".simulation_ipc", "SimulationIPCClient"),
    "SimulationIPCServer": (".simulation_ipc", "SimulationIPCServer"),
    "IPCCommand": (".simulation_ipc", "IPCCommand"),
    "IPCResponse": (".simulation_ipc", "IPCResponse"),
    "CommandType": (".simulation_ipc", "CommandType"),
    "CommandStatus": (".simulation_ipc", "CommandStatus"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
