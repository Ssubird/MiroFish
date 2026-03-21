# `world_v2_market` 日常使用手册

## 1. 当前主运行时

当前默认运行模式是 `world_v2_market`。默认主线阶段为：

1. `generator_opening`
2. `social_propagation`
3. `plan_synthesis`
4. `final_decision`
5. `await_result`
6. `settlement`
7. `postmortem`

默认 shipped 的 LLM 角色只有：

- `social_consensus_feed`
- `purchase_value_guard`
- `purchase_coverage_builder`
- `purchase_ziwei_conviction`
- `purchase_chair`

`purchase_chair` 会在 `plan_synthesis` 收口购买方案，并在 `final_decision` 产出最终预测。当前 shipped 主线没有默认 `judge` 层，也没有单独的 `decision` 层。

## 2. 入口接口

### 推进 world

- `POST /api/lottery/world/start`
  - 创建或续跑 session，本质上会进入同一套推进逻辑
- `POST /api/lottery/world/advance`
  - 推进一轮主线；如果上一轮已可结算，会先结算再推进下一轮

### 查询配置与运行状态

- `GET /api/lottery/execution/registry`
  - 查看 provider / model / profile 注册表
- `GET /api/lottery/agent-fabric/registry`
  - 查看当前 Agent Fabric 解析结果与导出快照
- `GET /api/lottery/world/runtime-readiness`
  - 查看当前 runtime backend、模型可用性、Kuzu 状态等

## 3. `visible_through_period` 的语义

`visible_through_period` 决定这轮 world 能看见的历史上界。

规则是：

- world 只能读取 `<= visible_through_period` 的已开奖历史
- 下一期目标默认是“`visible_through_period` 之后的第一期”
- `settlement` 只会在该目标期已经开奖时发生

例子：

- `visible_through_period=2026065`
  - world 只能看见到 `2026065`
  - 默认预测 `2026066`

## 4. 当前阶段职责

### `generator_opening`

- 运行 Python generator 组
- 产出 `signal_boards`
- 刷新共享块里的初始 `market_board`

### `social_propagation`

- 由 `social_consensus_feed` 把 generator 板面压缩为市场摘要
- 写入 `social_feed`
- 把 `market_board` 刷新成可供购买层消费的市场摘要版

### `plan_synthesis`

- 3 个购买人格分别给出可执行购买方案
- `purchase_chair` 读取人格方案与共享板面，收口为 `final_plan`
- 写入 `purchase_board`

### `final_decision`

- 默认 shipped 逻辑不再引入额外的终判 agent
- runtime 以 `purchase_chair` 为 owner，把 `final_plan` 收敛成 `final_decision`
- 这一阶段会写出最终主号、备选号、采用的策略组和最终理由

### `await_result`

- 说明本轮预测已完成，等待开奖

### `settlement`

- 目标期开奖后对 `final_decision` 与购买方案进行结算

### `postmortem`

- 生成最新复盘结果，更新 `issue_ledger` 和报告产物

## 5. 当前 agent 布局简表

### 市场摘要层

- `social_consensus_feed`
  - `group: social`
  - `phase: social_propagation`
  - 只负责压缩市场主叙事，不负责买票

### 购买人格层

- `purchase_value_guard`
  - 偏价值密度与防拥挤
- `purchase_coverage_builder`
  - 偏覆盖效率与票型结构
- `purchase_ziwei_conviction`
  - 偏紫微信号与混合 conviction

### 主席层

- `purchase_chair`
  - `phases: [plan_synthesis, final_decision]`
  - 负责收口 `final_plan`
  - 负责产出 `final_decision`
  - 当前也是默认最终 owner

## 6. 执行绑定与模型 / Provider 选择

模型和 provider 的注册仍由：

- [execution_config.yaml](E:/MoFish/MiroFish/backend/app/services/lottery/execution_config.yaml)
- 环境变量中的 `LLM_*`

共同决定。

Agent Fabric 只在 agent 级别引用 `profile_id`。运行时解析后的结果会写进 session 的：

- `resolved_execution_bindings`

前端里要区分两层：

- “默认模型”下拉
  - 影响默认 provider 路线
- `Execution Bindings`
  - 用于按 group 或按 agent 覆盖 profile

默认 shipped group 只显示：

- `data`
- `metaphysics`
- `hybrid`
- `social`
- `purchase`

## 7. Signal Board / Shared Memory / Result Line

### `signal_boards`

- generator 层的标准输出面
- 是购买主线最底层的原始信号面

### 关键 shared memory

- `current_issue`
- `visible_draw_history_digest`
- `market_board`
- `social_feed`
- `purchase_board`
- `handbook_principles`
- `final_decision_constraints`
- `report_digest`
- `rule_digest`
- `purchase_budget`

### 关键结果字段

- `latest_purchase_plan`
  - 当前主购买方案
- `latest_prediction.final_decision`
  - 当前官方最终预测
- `resolved_execution_bindings`
  - 当前 session 的实际执行绑定
- `agent_state`
  - 每个 agent 的最近活动、绑定文档与执行信息

## 8. 本地开发与 no-MCP

默认建议使用 `Letta + no-MCP`。

关键环境变量：

- `LOTTERY_WORLD_ALLOW_NO_MCP=true`
- `LOTTERY_WORLD_NO_MCP_BACKEND=auto|letta|local`
- `LETTA_BASE_URL=...`

默认选择逻辑：

- `LOTTERY_WORLD_NO_MCP_BACKEND` 未设置时，默认是 `auto`
- 如果 `auto` 且存在 `LETTA_BASE_URL`，实际走 `letta_no_mcp`
- 如果 `auto` 且没有 `LETTA_BASE_URL`，才走 `local_no_mcp`

Kuzu 在 no-MCP 模式下依然会用到，但用途是：

- 工作区图谱同步
- runtime projection
- 前端图谱观察面

不是默认 agent 工具链。

## 9. 常用 API 示例

### 新开或续跑一轮

```json
POST /api/lottery/world/advance
{
  "runtime_mode": "world_v2_market",
  "pick_size": 5,
  "budget_yuan": 50,
  "visible_through_period": "2026065",
  "strategy_ids": ["cold_rule", "hot_rule"]
}
```

### 查看 Agent Fabric

```text
GET /api/lottery/agent-fabric/registry
```

### 查看执行注册表

```text
GET /api/lottery/execution/registry
```

## 10. 常见日常操作流程

### 跑一轮预测

1. 先确认 `runtime-readiness` 为 ready
2. 选择 `visible_through_period`
3. 检查预算和执行绑定
4. 调 `world/advance`
5. 查看 `latest_prediction.final_decision`

### 查看当前 agent 实际吃了什么

1. 打开 `GET /api/lottery/agent-fabric/registry`
2. 看目标 agent 的 `prompt assets`
3. 再看 session 的 `agent_state[agent_id].bound_prompt_docs`
4. 如果需要核对实际发送 prompt，检查运行日志和本地 runtime 记录

### 切换不同 provider

1. 在 `.env` 或 `execution_config.yaml` 中注册 provider / profile
2. 用 `Execution Bindings` 按 group 或 agent 绑定 `profile_id`
3. 查看 session 中的 `resolved_execution_bindings` 是否符合预期
