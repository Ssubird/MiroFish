# Data Group Runtime

数据组当前仍然保留在 Python 实现里，没有迁移到声明式执行层，但已经进入统一导出快照，方便你对照 LLM 角色一起看。

## 真实入口

- `backend/app/services/lottery/agents/data_agents.py`
  - 数据组 agent 定义
- `backend/app/services/lottery/catalog.py`
  - 挂到 `build_strategy_catalog()`
- `backend/app/services/lottery/world_v2_runtime.py`
  - 在 `generator_opening` 阶段按 group 独立运行

## 当前数据组 Agent

- `cold_50`
- `miss_120`
- `momentum_60`
- `structure_90`
- `recent_board_50`

## 运作方式

- 它们不走 `agent_fabric/agents/*.yaml`
- 它们仍然使用 `StrategyAgent.predict(...)`
- 它们的输出会进入 signal board，再被 social / judge / purchase / decision 读取
- 它们会出现在 `generated/agent_fabric_snapshot.*` 的 data inventory 中

## 你现在应该怎么改

- 如果你要改数据组算法：继续改 `data_agents.py`
- 如果你要改 LLM 角色接收什么：改 `agent_fabric/agents/*.yaml`
- 如果你要看数据组和 LLM 角色如何衔接：看 `generated/agent_fabric_snapshot.md`
