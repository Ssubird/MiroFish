# `ziweidoushu` 工作区总览

## 1. 这个目录是做什么的

`ziweidoushu/` 是 `world_v2_market` 的领域工作区。这里同时承载：

- 研究输入：开奖数据、知识文档、提示词
- 运行配置：Agent Fabric 的 `manifest.yaml`、`agents/*.yaml`、`prompts/*.md`
- 运行输出：`generated/`、`reports/`、`.world_state/`

当前默认 shipped 运行主线是：

`generator_opening -> social_propagation -> plan_synthesis -> final_decision -> await_result -> settlement -> postmortem`

默认 shipped 的 LLM 角色只有两层：

- `social`
- `purchase`

其中 `purchase_chair` 同时负责：

- 在 `plan_synthesis` 阶段收口购买方案
- 在 `final_decision` 阶段产出最终预测

## 2. 目录结构

- `agent_fabric/`
  - 声明式 agent 配置根目录
- `data/`
  - 开奖数据、派生数据
- `knowledge/`
  - 提示词、知识文档、学习材料
- `generated/`
  - Agent Fabric 快照等导出文件
- `reports/`
  - 预测报告、回测报告、分期报告
- `.world_state/`
  - world session、timeline、result 等运行态文件

## 3. 推荐阅读顺序

1. [USAGE.md](E:/MoFish/MiroFish/ziweidoushu/USAGE.md)
   日常怎么跑、怎么看、怎么调。
2. [WORLD_V2_DESIGN.md](E:/MoFish/MiroFish/ziweidoushu/WORLD_V2_DESIGN.md)
   为什么这样设计，主线边界是什么。
3. [WORLD_V2_RUNTIME_GUIDE.md](E:/MoFish/MiroFish/ziweidoushu/WORLD_V2_RUNTIME_GUIDE.md)
   运行模式、排障入口、状态核对方法。
4. [AGENT_ARCHITECTURE.md](E:/MoFish/MiroFish/ziweidoushu/AGENT_ARCHITECTURE.md)
   Agent Fabric、输入绑定、共享记忆、扩展方式。

## 4. 当前运行时一句话摘要

当前默认基线是 `Letta + no-MCP`。Kuzu 仍会在每轮推进前同步工作区图谱，并承担运行态投影与只读观察面，但不作为默认 no-MCP 决策链里的 agent 工具。

## 5. 以代码为准

本目录中的设计文档、使用文档、架构文档都以当前代码实现为准。若文档与代码冲突，应优先核对：

- [world_v2_runtime.py](E:/MoFish/MiroFish/backend/app/services/lottery/world_v2_runtime.py)
- [agent_fabric_registry.py](E:/MoFish/MiroFish/backend/app/services/lottery/agent_fabric_registry.py)
- [manifest.yaml](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/manifest.yaml)
- [agents](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/agents)
