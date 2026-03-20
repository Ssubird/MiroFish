# World_v2 下一步架构整理

## 这次已经落地的前端方向

- `LotteryLabView` 只保留页面壳、主视图切换和状态条。
- 左侧图谱区收敛到 `LotteryWorldCanvasStage.vue`。
- 右侧工作台收敛到 `LotteryWorldWorkbench.vue`。
- 主布局回到原项目的 `graph / split / workbench` 思路，不再自己维护多套三栏比例。

这一步的价值是先把“页面壳”和“业务卡片”拆开，后面要继续换 UI，不需要再改一整页模板。

## 后端下一步最值得拆的 4 层

### 1. Session Store

目标：

- 只负责 `session.json`、`timeline.jsonl`、`result.json` 的读写。
- 只提供 `load / save / append_timeline / write_result`。

原因：

- 现在 `world_v2_runtime.py` 同时管状态、执行、持久化，调试成本太高。
- 预测跑慢、会话兼容、回放错误时，很难判断是执行问题还是存储问题。

建议文件：

- `backend/app/services/lottery/world_session_store.py`

### 2. Phase Runner

目标：

- 每个阶段一个明确执行器。
- 例如 `generator_opening`、`social_propagation`、`market_rerank`、`plan_synthesis`、`handbook_final_decision`、`settlement`。

原因：

- 现在 phase 切换逻辑和 phase 内业务混在同一个 runtime 文件里。
- 将来你想替换某一段 agent 关系，最好只动对应 phase runner。

建议目录：

- `backend/app/services/lottery/world_phases/`

建议文件：

- `generator_phase.py`
- `social_phase.py`
- `judge_phase.py`
- `purchase_phase.py`
- `decision_phase.py`
- `settlement_phase.py`

### 3. Agent Fabric Adapter

目标：

- `AgentFabricRegistry` 只负责“配置规格”。
- 新增一层 adapter，专门把 fabric spec 转成 runtime 可执行角色。

原因：

- 现在 registry 和 runtime 之间还是偏紧耦合。
- 你后面想改 agent 关系、共享可见性、profile 绑定时，最好不碰 world 主流程。

建议文件：

- `backend/app/services/lottery/agent_fabric_adapter.py`

建议职责：

- 生成 phase 参与表
- 生成 visibility map
- 生成 shared memory 订阅表
- 生成 prompt payload
- 生成 execution binding request

### 4. Projection / Read Model

目标：

- 前端拿到的是“页面友好结构”，不是 runtime 内部状态拼装残片。

原因：

- 现在前端很多卡片都在自己猜 session 结构。
- 一旦后端字段换名，页面会一起碎。

建议接口：

- `/api/lottery/world/current`
- `/api/lottery/world/:id`
- `/api/lottery/world/:id/graph`
- `/api/lottery/world/:id/timeline`
- `/api/lottery/agent-fabric/registry`

建议增加一个统一投影视图：

- `backend/app/services/lottery/world_projection.py`

建议职责：

- 生成 header summary
- 生成 control panel 所需只读数据
- 生成 inspector 所需只读数据
- 生成 graph / timeline / artifacts 的轻量摘要

## 前端下一步最值得拆的 3 层

### 1. Shell 层

当前已经开始拆：

- `LotteryLabView.vue`
- `LotteryWorldCanvasStage.vue`
- `LotteryWorldWorkbench.vue`

规则：

- 壳层不直接解释业务。
- 只负责布局、模式切换、总入口动作。

### 2. Studio State 层

当前主要在：

- `useLotteryWorldStudio.js`

下一步建议继续拆成：

- `useLotteryWorldRunState.js`
- `useLotteryExecutionBindings.js`
- `useLotterySelectionState.js`
- `useLotteryRuntimeReadiness.js`

原因：

- 现在一个 composable 同时管运行、模型、图谱、选择、执行绑定，后面会继续膨胀。

### 3. Read Panel 层

目标：

- 控制面板和详情面板尽量只吃“整理过的数据”。
- 不要在组件里再做过深的数据兜底和结构猜测。

优先级最高的新增只读面板：

- Agent Fabric Registry 面板
- Data Group Inventory 面板
- Execution Bindings Summary 面板

## 前端风格约束

后面彩票页继续改时，建议固定遵守这几个规则：

- 主布局只保留 `graph / split / workbench` 三态，不再加新的顶层布局模式。
- 主面板最多两块：图谱区、工作台区。
- 工作台内部切 `双栏 / 控制 / 详情`，不要回到三栏。
- 任何长文本卡片必须允许换行和滚动，不能靠固定高度硬顶。
- 页面状态信息统一放顶部状态条，不要每个卡片都重复一份“当前阶段”。

## 你后面改 agent 时，最舒服的目标状态

理想状态应该是这样：

1. 只改 `agent_fabric/manifest.yaml` 和 `agent_fabric/agents/*.yaml`
2. 保存后重新推进 world
3. 前端的 Agent Fabric 面板直接看到新关系
4. runtime 不需要改一行硬编码

如果还做不到这 4 步，说明 agent 配置层和执行层还没彻底解耦。
