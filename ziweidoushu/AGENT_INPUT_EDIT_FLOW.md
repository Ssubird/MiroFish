# Agent 输入修改流程

这份文档专门说明：如何给 `world_v2` 里的单个 agent 追加完整提示词文件、原始数据文件，以及如何验证它是否真的生效。

## 这次已经改好的示例

当前示例 agent 是 `handbook_decider`，配置文件在 `agent_fabric/agents/handbook_decider.yaml`。

它现在会额外完整输入两份内容：

- `knowledge/prompts/prompt.md`
- `data/draws/keno8_predict_data.json`

对应配置如下：

```yaml
prompt:
  blocks:
    - type: prompt_file
      path: final_decider_doctrine.md
    - type: workspace_document
      name: prompt.md
    - type: workspace_file
      path: data/draws/keno8_predict_data.json
```

## 你以后怎么改

### 1. 改某个 agent 吃哪些输入

打开对应的 agent YAML：

- `agent_fabric/agents/social_consensus_feed.yaml`
- `agent_fabric/agents/consensus_judge.yaml`
- `agent_fabric/agents/purchase_chair.yaml`
- `agent_fabric/agents/handbook_decider.yaml`

主要改 `prompt.blocks` 和 `document_refs`。

### 2. 常用输入方式

`prompt_file`

- 读取 `agent_fabric/prompts/*.md`
- 适合放可复用的角色 doctrine

`workspace_document`

- 读取已经被仓库识别为知识文档的文件
- 目前主要是 `knowledge/`、`reports/` 下的 `.md/.txt`
- 用 `name` 指定文档名，比如 `prompt.md`

`workspace_file`

- 直接读取 `ziweidoushu/` 工作区里的原始文件
- 用 `path` 指定相对路径，比如 `data/draws/keno8_predict_data.json`
- 适合 JSON、原始数据、临时结构化文件

`shared_memory`

- 读取当前 session 的共享记忆块
- 适合让 agent 拿到 runtime 内部聚合结果

### 3. 如何把完整 JSON 喂给另一个 agent

直接在那个 agent 的 `prompt.blocks` 里追加：

```yaml
- type: workspace_file
  path: data/draws/keno8_predict_data.json
```

### 4. 如何把完整 prompt.md 喂给另一个 agent

如果是知识文档方式，追加：

```yaml
- type: workspace_document
  name: prompt.md
```

### 5. 如何新增一个新的同类 agent

在 `agent_fabric/agents/` 下复制一个现有 YAML，再修改这些字段：

- `agent_id`
- `display_name`
- `description`
- `behavior_template`
- `role_kind`
- `group`
- `phases`
- `profile_id`
- `prompt.blocks`

注意：

- `behavior_template` 必须和 `role_kind` 匹配
- `profile_id` 必须存在于 `backend/app/services/lottery/execution_config.yaml`
- `workspace_file.path` 必须是 `ziweidoushu/` 下的真实文件，不能越界到工作区外

## 自动分块规则

`workspace_document` 和 `workspace_file` 都会走同一套分块逻辑：

- 默认每块 2800 字符
- 按段落优先切分
- 太长的单段会继续硬切
- 不会静默截断
- 如果 `workspace_file` 是 `.json`，会先转成紧凑 JSON 再分块，字段和值不变，只去掉缩进和空白

所以像 `keno8_predict_data.json` 这种大文件，会被拆成多段 passage 送进 agent，而不是只取前面一截。

## 修改后如何生效

不需要重启进程。

下面这些入口每次都会重新从磁盘加载 `agent_fabric/`：

- `prepare_world_session`
- `POST /api/lottery/world/start`
- `POST /api/lottery/world/advance`
- `GET /api/lottery/agent-fabric/registry`

## 怎么验证是否真的喂进去了

### 看注册表快照

请求：

```text
GET /api/lottery/agent-fabric/registry
```

关注：

- `registry.agents[*].prompt_sources`
- `registry.agents[*].bound_documents`

如果是这次的配置，`handbook_decider` 应该能看到：

- `prompt.md`
- `data/draws/keno8_predict_data.json`

### 看运行时 session

在 world session 里关注：

- `session.agent_state.handbook_decider.prompt_sources`
- `session.agent_state.handbook_decider.bound_prompt_docs`
- `session.agent_state.handbook_decider.bound_prompt_passage_count`

如果 passage 数明显增加，说明整份 JSON 已经被分块注入。

## 这次改动的目标

这次先做了一个最直接的例子：让 `handbook_decider` 单独多吃两份完整输入。后续你要换成别的 agent，只需要改对应 YAML，不用再写 Python 逻辑。

## `keno8_predict_data.json` 完整性排查结果

这次顺手把仓库里所有和 `keno8_predict_data.json` 相关的代码路径也排查了一遍，结论是：

- 当前仓库里没有发现任何代码会把源文件 `ziweidoushu/data/draws/keno8_predict_data.json` 写回去。
- 目前看到的都是读取路径，或者把它的内容带入别的产物里。

### 当前主要读取路径

- `backend/app/services/lottery/repository.py`
  - `load_draws()`
  - `_load_draw_embedded_charts()`
- `backend/app/services/lottery/world_assets.py`
  - `build_world_asset_manifest()`
- `backend/app/services/lottery/agents/full_context_agent.py`
  - `_read_predict_data()`
- `backend/app/services/lottery/research_service.py`
  - `build_overview()` 只暴露文件路径，不写文件

### 容易误以为“它被改了”的地方

- `backend/tmp/world_debug_run/**`
  - 会生成 session、result、backtest 调试产物
- `ziweidoushu/generated/agent_fabric_snapshot.*`
  - 会记录 agent 绑定了哪些输入源
- 各类 issue report / world state / snapshot JSON
  - 这些文件会复制或引用数据内容，但不是回写源文件

### 如果你怀疑又被改了，先看什么

1. 先看源文件本身：

```text
ziweidoushu/data/draws/keno8_predict_data.json
```

2. 再看是不是其实在看这些运行产物：

```text
backend/tmp/world_debug_run/
ziweidoushu/generated/
```

3. 如果源文件确实变化了，但仓库里又找不到写入路径，那就更像是：

- 手工改动
- 仓库外脚本改动
- 同步工具、抓取脚本或外部流程覆盖

### 以后你自己怎么快速排查

```powershell
rg -n "keno8_predict_data\\.json|DRAW_DATA_FILE" backend frontend ziweidoushu
rg -n "write_text|write_bytes|json\\.dump" backend/app/services/lottery
```
