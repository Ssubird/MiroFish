# `world_v2_market` 设计说明

## 1. 设计目标与边界

`world_v2_market` 的目标不是做一个“所有角色都能无限扩张的论坛”，而是稳定产出面向购买决策的主线结果。

当前默认 shipped 设计目标是：

- generator 负责产出原始信号面
- social 负责压缩市场主叙事
- purchase 负责提出并收口购买方案
- `purchase_chair` 负责最终预测 owner

因此默认 shipped 主线被收口为：

`generator_opening -> social_propagation -> plan_synthesis -> final_decision -> await_result -> settlement -> postmortem`

## 2. 运行时入口与状态推进

外部入口保持不变：

- `POST /api/lottery/world/start`
- `POST /api/lottery/world/advance`

内部推进上：

1. 先确定可见历史窗口和目标期
2. 同步 Kuzu 工作区图谱
3. 构造本轮 context、加载 Agent Fabric、注册 session agents
4. 依次推进主线 phase
5. 如果目标期已经开奖，则执行 `settlement` 和 `postmortem`

## 3. 可见期模型

系统以 `visible_through_period` 作为唯一历史可见边界。

这个模型的意义是：

- 明确避免未来开奖泄漏
- 保证预测和结算都以同一条时间线前进
- 让回测、单轮推进、人工续跑都共用同一套语义

## 4. 阶段流转与职责分层

### `generator_opening`

- 运行 Python generator 策略
- 产出 `signal_boards`
- 不做购买结论

### `social_propagation`

- 由 `social_consensus_feed` 汇总市场主叙事
- 把 generator 输出压缩成购买层易消费的摘要

### `plan_synthesis`

- 购买人格分别给出可执行购买方案
- `purchase_chair` 汇总为 `final_plan`

### `final_decision`

- 默认 shipped 逻辑不新增额外终判层
- runtime 以 `purchase_chair` 为 owner，把 `final_plan` 收敛成 `final_decision`

### `await_result / settlement / postmortem`

- 等待开奖
- 结算
- 复盘

## 5. Generator 隔离原则

generator 组始终是 Python 规则侧。

它们的边界是：

- 只负责各自板面
- 不直接消费 Fabric LLM 角色
- 在 `generator_opening` 之前彼此隔离

这样做的目的，是让“原始信号面”和“市场 / 购买解释层”清楚分开。

## 6. 当前市场角色结构

默认 shipped 角色如下：

- `social_consensus_feed`
- `purchase_value_guard`
- `purchase_coverage_builder`
- `purchase_ziwei_conviction`
- `purchase_chair`

默认 shipped 只有两个活跃 group：

- `social`
- `purchase`

当前没有默认 shipped 的 `judge` 与 `decision` 层。

## 7. Agent Fabric 作为唯一真相源

当前运行时应以以下两类文件作为默认真相源：

- [manifest.yaml](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/manifest.yaml)
- [agents](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/agents)

它们负责：

- phase 顺序
- group 默认可见性与 shared memory
- agent roster
- prompt blocks
- document refs
- `profile_id`

`catalog.py` 只负责消费已解析出的 Fabric 结果与 Python generator，不再维护另一套默认主线语义。

## 8. Execution Fabric / Provider 绑定

模型执行绑定仍由：

- [execution_registry.py](E:/MoFish/MiroFish/backend/app/services/lottery/execution_registry.py)
- [execution_config.yaml](E:/MoFish/MiroFish/backend/app/services/lottery/execution_config.yaml)
- 环境变量 `LLM_*`

共同决定。

Agent Fabric 只在 agent 级别引用 `profile_id`，session 真正生效的执行结果会落到：

- `resolved_execution_bindings`

## 9. Shared Memory 模型

默认主线使用这些核心 shared blocks：

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

边界设计是：

- `market_board` 面向市场摘要层和购买层
- `purchase_board` 面向主席收口与最终预测
- `handbook_principles` 只给需要 handbook 的购买角色

## 10. Game Kernel、Kuzu、报告、缓存

### Game Kernel

- 购买方案合法性、价格计算、结算都由 game definition 负责

### Kuzu

- 负责工作区图谱同步
- 负责 runtime projection 和前端观察面
- 在默认 `no-MCP` 主线里不是 agent 工具链

### 报告

- `reports/` 输出回测报告、分期报告、issue ledger

### Cache

- 同 issue、同 prompt 的 agent 结果会写入 session / runtime cache，避免重复请求

## 11. 前端原则

这轮前端不追求重新设计整个工作台，只做语义收口：

- phase 名称必须对应当前主线
- 活跃 agent 列表只显示 shipped roster
- Kuzu 文案只表达“图谱 / 投影 / 观察面”
- 不把旧的 judge / decision 当作默认运行角色继续展示

## 12. 后续演进方向

当前默认主线已经收口，但 runtime 仍有继续拆边界的空间。后续优先方向是：

1. `PhaseRunner`
   只管阶段推进和 phase 状态写回。
2. `AgentAssembler`
   只管把 generator 与 Fabric agent 组装成 session agents。
3. `PromptBindingService`
   只管 prompt blocks、文档引用、chunking 与 bound docs 元信息。
4. `SharedMemoryService`
   只管 shared blocks 的生成、同步与可见性。
5. `FinalDecisionService`
   只管从 `final_plan` 到 `final_decision` 的收敛。

这个方向的目标不是增加更多角色，而是让扩展购买人格、替换 prompt、切换 provider 时都落在清晰边界内。
