# `world_v2_market` 运行维护与排障手册

## 1. 当前运行模式

`world_v2_market` 当前默认推荐使用：

- `Letta + no-MCP`

这条基线的特点是：

- Letta 负责 agent 容器与消息发送
- Agent Fabric 负责 prompt / 文档 / 共享块绑定
- Kuzu 负责图谱同步和运行态投影
- 默认不依赖 MCP 工具链参与 agent 决策

## 2. 环境变量与 backend 模式

关键环境变量：

- `LOTTERY_WORLD_ALLOW_NO_MCP`
- `LOTTERY_WORLD_NO_MCP_BACKEND`
- `LETTA_BASE_URL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`

`LOTTERY_WORLD_NO_MCP_BACKEND` 支持：

- `auto`
- `letta`
- `local`

默认解析逻辑：

1. `LOTTERY_WORLD_ALLOW_NO_MCP=true`
2. `LOTTERY_WORLD_NO_MCP_BACKEND` 未设置时按 `auto`
3. `auto` 且存在 `LETTA_BASE_URL`
   - 实际走 `letta_no_mcp`
4. `auto` 且没有 `LETTA_BASE_URL`
   - 实际走 `local_no_mcp`

## 3. 关键 API 检查

### 检查 runtime 是否 ready

```text
GET /api/lottery/world/runtime-readiness
```

### 检查执行注册表

```text
GET /api/lottery/execution/registry
```

### 检查 Agent Fabric 解析结果

```text
GET /api/lottery/agent-fabric/registry
```

### 推进一步 world

```text
POST /api/lottery/world/advance
```

## 4. Session 文件与产物位置

运行态主要落在：

- [\.world_state](E:/MoFish/MiroFish/ziweidoushu/.world_state)
- [reports](E:/MoFish/MiroFish/ziweidoushu/reports)
- [generated](E:/MoFish/MiroFish/ziweidoushu/generated)

常看文件：

- `session.json`
- `timeline.jsonl`
- `result.json`

关键顶层字段：

- `current_phase`
- `latest_purchase_plan`
- `final_decision`
- `resolved_execution_bindings`
- `agent_state`

## 5. 常见故障分诊顺序

建议固定按这个顺序查：

1. `runtime-readiness` 是否 ready
2. Kuzu 是否已同步
3. `agent-fabric/registry` 是否解析成了你预期的 roster
4. `resolved_execution_bindings` 是否命中了你预期的 profile
5. `agent_state[*].bound_prompt_docs` 是否包含你想发的文档
6. `timeline.jsonl` 是否有明确的失败 phase 和错误内容

## 6. `readiness` / 模型列表 / session failed

### `runtime-readiness` 不 ready

先查：

- `LETTA_BASE_URL` 是否可访问
- 默认 provider 是否可用
- `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME` 是否完整

### 前端一开始读不到模型

先查：

- `GET /api/lottery/execution/registry`
- `GET /api/lottery/world/runtime-readiness`

当前前端会自动预热模型列表，但 provider 未 ready 时仍可能短暂显示空状态。

### session 进入 `failed`

优先看：

- `session.error`
- `execution_log`
- `timeline.jsonl`

不要先看文档，先看运行态里记录的失败 phase。

## 7. Kuzu 检查

Kuzu 在默认 no-MCP 主线里的职责是：

- 工作区图谱同步
- runtime projection
- 前端图谱读模型

它不是默认 no-MCP agent 工具链。

要核对 Kuzu 是否正常：

1. 看 `overview.kuzu_graph_status`
2. 看前端 Kuzu 状态卡片
3. 手动触发一次 `sync-kuzu`
4. 再推进 world

如果预测流程不动，先排除 Kuzu 未同步导致的前置状态问题。

## 8. Shared Memory 检查

最常见的共享块包括：

- `current_issue`
- `market_board`
- `social_feed`
- `purchase_board`
- `handbook_principles`
- `final_decision_constraints`

如果怀疑 agent 没看到正确上下文，先查：

- `world_session.shared_memory`
- `agent_state[agent_id]`

## 9. Prompt 注入与 bound docs 检查

要确认某个 agent 实际绑定了什么，按这个顺序看：

1. `GET /api/lottery/agent-fabric/registry`
2. `session.agent_state[agent_id].bound_prompt_docs`
3. `session.agent_state[agent_id].bound_prompt_passage_count`
4. `session.agent_state[agent_id].prompt_sources`

当前默认重点 agent：

- `purchase_chair`
  - 绑定 `purchase_planner_doctrine.md`
  - 绑定 `prompt.md`
  - 绑定 `data/draws/keno8_predict_data.json`
  - 绑定 `lottery_handbook_deep_notes.md`
- `purchase_ziwei_conviction`
  - 绑定 handbook

默认 shipped 里，只有 `purchase_ziwei_conviction` 和 `purchase_chair` 会吃 handbook。

## 10. 本地运行时排查链路

如果你怀疑 `local_no_mcp` 和 `letta_no_mcp` 行为不一致，建议：

1. 先看 `runtime-readiness` 返回的 `backend`
2. 再看 session `execution_log` 里是 `letta_no_mcp_mode` 还是 `local_no_mcp_mode`
3. 再核对同一个 agent 的 `bound_prompt_docs`

当前默认 shipped `final_decision` 不是额外再调一个独立终判 agent；它是以 `purchase_chair` 为 owner，把 `final_plan` 收敛成 `final_decision`。如果你看到 token 消耗异常低，优先排查的是 prompt 绑定与实际发送内容，而不是去找一个不存在的默认终判层。

## 11. 无结果展示时怎么查

### 有 `latest_purchase_plan`，没有 `final_decision`

说明问题大概率卡在 `final_decision` 阶段或它之前的状态写回。

### 连 `latest_purchase_plan` 都没有

优先查：

- `social_propagation` 是否完成
- `plan_synthesis` 是否失败
- 购买人格是否有返回可执行方案

### 前端图谱或阶段名不对

优先查：

- `session.current_phase`
- `latest_prediction.coordination_trace`
- 前端是否拿到了新的 `phaseLabel` 和 graph phase order

## 12. 快速核对清单

只想快速判断当前这轮是否正常，可以看这 6 项：

1. `current_phase`
2. `predicted_period`
3. `latest_purchase_plan.status`
4. `latest_prediction.final_decision.numbers`
5. `resolved_execution_bindings.purchase_chair`
6. `agent_state.purchase_chair.bound_prompt_docs`
