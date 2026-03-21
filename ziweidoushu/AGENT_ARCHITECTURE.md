# Agent / Fabric / 输入绑定架构

## 1. 当前总体结构

当前 `world_v2_market` 的默认 shipped 结构是：

- generator：Python 规则策略
- social：市场摘要层
- purchase：购买人格层 + 主席层

当前默认主线没有独立的 `judge` 层，也没有独立的 `decision` 层。

`purchase_chair` 同时处在：

- `plan_synthesis`
- `final_decision`

所以默认 shipped 的最终预测 owner 也是 `purchase_chair`。

## 2. 当前活跃 agent 清单

### `social_consensus_feed`

- `group: social`
- `phase: social_propagation`
- 用途：把市场主叙事压缩成购买层可读的摘要

### `purchase_value_guard`

- `group: purchase`
- `phase: plan_synthesis`
- 用途：强调价值密度、防拥挤和预算内执行

### `purchase_coverage_builder`

- `group: purchase`
- `phase: plan_synthesis`
- 用途：强调覆盖效率、票型结构和对冲池

### `purchase_ziwei_conviction`

- `group: purchase`
- `phase: plan_synthesis`
- 用途：强调紫微信号与混合 conviction

### `purchase_chair`

- `group: purchase`
- `phases: [plan_synthesis, final_decision]`
- 用途：
  - 汇总购买人格方案得到 `final_plan`
  - 作为默认最终 owner 产出 `final_decision`

## 3. 数据组如何运行

数据组、玄学组、混合组仍然是 Python builder 侧，不在 `agent_fabric/agents/*.yaml` 中声明。

它们的边界是：

- 运行在 `generator_opening`
- 输出 `signal_boards`
- 后续由 social / purchase 层消费

所以你在扩展购买人格时，不需要把这些 generator 搬进 Fabric。

## 4. Agent Fabric 目录结构

配置根目录：

- [agent_fabric](E:/MoFish/MiroFish/ziweidoushu/agent_fabric)

固定分层：

- [manifest.yaml](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/manifest.yaml)
  - phase 与 group 默认值
- [agents](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/agents)
  - 每个 agent 一个 YAML
- [prompts](E:/MoFish/MiroFish/ziweidoushu/agent_fabric/prompts)
  - 可复用 prompt 片段

## 5. `manifest.yaml` 负责什么

当前 shipped `manifest.yaml` 负责：

- phase 顺序
- group 默认 `profile_id`
- group 默认 `visible_groups`
- group 默认 `shared_memory_keys`

当前 shipped 只定义：

- `social_propagation`
- `plan_synthesis`
- `final_decision`

和两个活跃 group：

- `social`
- `purchase`

## 6. `agents/*.yaml` 负责什么

每个 agent YAML 负责：

- `agent_id`
- `display_name`
- `behavior_template`
- `role_kind`
- `group`
- `phases`
- `profile_id`
- `prompt.blocks`
- `document_refs`
- `shared_memory_keys`
- `visible_groups`
- `visible_agents`
- `dialogue_policy`
- `limits`
- `metadata`

运行时真正用到的是解析后的 `ResolvedAgentSpec`，不是原始 YAML 文本。

## 7. Prompt block 类型

当前支持的 block 类型：

- `static_text`
- `prompt_file`
- `workspace_document`
- `workspace_file`
- `runtime_text`
- `shared_memory`

含义分别是：

### `prompt_file`

读取 `agent_fabric/prompts/*.md`

### `workspace_document`

读取知识文档注册表中的文档，例如 `prompt.md`

### `workspace_file`

直接读取工作区里的原始文件，例如：

- `data/draws/keno8_predict_data.json`

### `runtime_text`

由 runtime 动态生成的块，例如：

- `purchase_rule_block`
- `purchase_schema`

## 8. 如何修改单个 agent 输入

目标文件：

- `agent_fabric/agents/<agent>.yaml`

最常改的是：

- `prompt.blocks`
- `document_refs`
- `profile_id`
- `shared_memory_keys`
- `visible_groups`

### 例子：给 `purchase_chair` 追加完整 JSON

```yaml
prompt:
  blocks:
    - type: workspace_file
      path: data/draws/keno8_predict_data.json
```

### 例子：给 `purchase_chair` 追加完整 `prompt.md`

```yaml
prompt:
  blocks:
    - type: workspace_document
      name: prompt.md
```

## 9. 如何绑定完整文档 / 原始 JSON / runtime block

### 完整知识文档

用：

```yaml
- type: workspace_document
  name: prompt.md
```

### 完整原始文件

用：

```yaml
- type: workspace_file
  path: data/draws/keno8_predict_data.json
```

### runtime 生成块

用：

```yaml
- type: runtime_text
  name: purchase_rule_block
```

## 10. 自动分块规则与验证

大文本不会静默截断，而是按当前 passage 规则自动分块。

当前默认 passage 字符限制来自：

- `prompt_char_limit`

shipped 默认是 `2800` 字符一段。

验证方式：

1. 查看 `GET /api/lottery/agent-fabric/registry`
2. 查看 session 的 `agent_state[agent_id].bound_prompt_passage_count`
3. 查看 `agent_state[agent_id].prompt_sources`

## 11. 当前 handbook 绑定策略

handbook 当前只绑定给：

- `purchase_ziwei_conviction`
- `purchase_chair`

这样做是为了避免 handbook 被无差别广播给所有角色，浪费 token。

## 12. 当前默认大输入策略

### `purchase_chair`

当前默认会读取：

- `purchase_planner_doctrine.md`
- `prompt.md`
- `data/draws/keno8_predict_data.json`
- `lottery_handbook_deep_notes.md`

### `purchase_ziwei_conviction`

当前默认会读取：

- 自己的人格 prompt
- `lottery_handbook_deep_notes.md`

其余 shipped 角色默认不读 handbook。

## 13. Shared Memory 所有权与可见性

默认 shipped 的核心块：

- `market_board`
- `social_feed`
- `purchase_board`
- `final_decision_constraints`

大致所有权是：

- `market_board`
  - generator + social 共同刷新
- `social_feed`
  - social 层刷新
- `purchase_board`
  - `purchase_chair` 刷新
- `final_decision_constraints`
  - runtime 按当前期数、预算和 owner 生成

当前 shipped `visible_groups` 只围绕：

- `data`
- `metaphysics`
- `hybrid`
- `social`
- `purchase`

## 14. `purchase_chair` 的最终预测机制

默认 shipped `final_decision` 有一个重要特点：

- 它不会再额外调起一个单独终判 agent
- runtime 直接以 `purchase_chair` 为 owner，从 `final_plan` 收敛出 `final_decision`

这意味着：

- 默认 token 消耗不会再多出一层独立终判
- `final_decision.decision_owner` 默认就是 `purchase_chair`

## 15. 当前可扩展的入口

如果你后面要继续扩展，建议优先从这三类入手：

### 新增购买人格

- 新建一个 `purchase` 组 YAML
- 放进 `plan_synthesis`
- 绑定自己的 prompt blocks

### 替换 `purchase_chair` 输入

- 直接改 `purchase_chair.yaml`
- 调整 `prompt.blocks`、`document_refs`、`profile_id`

### 调整模型绑定

- 改 `profile_id`
- 或通过 session `Execution Bindings` 覆盖

## 16. 关于保留扩展类型

当前解析器仍支持更广的 `role_kind` / `behavior_template` 组合，用于后续扩展。

但就 shipped 默认主线来说，当前真正启用的只有：

- `social_discussion`
- `purchase_planner`

如果后面你决定重新引入别的层，应该先改设计，再改 shipped manifest，而不是先在文档里假设它已经是默认主线的一部分。
