# Agent Fabric Authoring

`world_v2_market` 的 LLM 角色现在统一由 `agent_fabric/` 驱动。第一阶段接管 `social`、`judge`、`purchase`、`decision` 四类 agent，规则型数据组仍保持 Python builder，但会出现在统一快照里。

## 目录结构

- `agent_fabric/manifest.yaml`
  - phase 和 group 默认值
- `agent_fabric/agents/*.yaml`
  - 单个 agent 定义
- `agent_fabric/prompts/*.md`
  - 可复用 prompt 片段
- `generated/agent_fabric_snapshot.{md,json}`
  - 当前配置导出快照

## Agent 字段

- `agent_id`
  - 运行时唯一 ID
- `behavior_template`
  - 首期只支持 `social_discussion`、`judge_panel`、`purchase_planner`、`final_decider`
- `role_kind` / `group`
  - 必须匹配
- `phases`
  - 当前 agent 参与哪些阶段
- `profile_id`
  - 绑定到 `execution_config.yaml` 中的 profile
- `prompt.blocks`
  - 块级 prompt 装配，不支持整段 prompt 覆盖
- `document_refs`
  - 直接绑定 workspace 文档名
- `shared_memory_keys`
  - 允许同步到 agent block 的共享记忆
- `visible_groups` / `visible_agents`
  - 限制阶段内可见的组和 agent

## Prompt Block 类型

- `static_text`
  - 直接写文本
- `prompt_file`
  - 读取 `agent_fabric/prompts/*.md`
- `workspace_document`
  - 读取 `knowledge/*` 或 `reports/*` 中已加载的文档
- `workspace_file`
  - 直接读取 `ziweidoushu/` 工作区里的任意原始文件，并按 2800 字符规则自动分块
- `runtime_text`
  - 读取运行时内置块，目前开放 `purchase_rule_block`、`purchase_schema`、`comment_schema`、`debate_schema`
- `shared_memory`
  - 将共享记忆键作为 prompt 资产块注入

## 生效方式

- `prepare_world_session`
- `POST /api/lottery/world/start`
- `POST /api/lottery/world/advance`
- `GET /api/lottery/agent-fabric/registry`

这些入口都会从磁盘重新加载 `agent_fabric/`，所以你修改 YAML 后不需要重启进程。
