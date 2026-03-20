# Lottery World Usage

## Current Runtime

- primary runtime: `world_v2_market`
- public action: `POST /api/lottery/world/advance`
- setup endpoint: `POST /api/lottery/world/prepare`
- execution catalog: `GET /api/lottery/execution/registry`
- removed: `/api/lottery/world/evolution`
- removed: `iterations`
- kept: `agent_dialogue_rounds`
- frontend discussion rounds max: `5`

## Visible-Through Workflow

The period selector means `visible_through_period`.

Rules:

- select `2026063`
  - visible data ends at `2026063`
  - the system predicts `2026064`
  - `2026064` actual numbers remain hidden
- select `2026064` next time
  - if `2026064` actual data already exists, the system first settles and postmortems `2026064`
  - then it predicts `2026065`

Repeated clicks on the same `visible_through_period` with unchanged draw data do not create duplicate predictions or duplicate hit records.

## Runtime Phases

Prediction cycle:

1. `generator_opening`
2. `social_propagation`
3. `market_rerank`
4. `plan_synthesis`
5. `handbook_final_decision`
6. `await_result`

Settlement cycle:

1. `settlement`
2. `postmortem`

## Agent Layout

Generator layer:

- `cold_50`
- `miss_120`
- `momentum_60`
- `structure_90`
- `recent_board_50`
- `metaphysics_fused_board`
- `hybrid_fused_board`

Market layer:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`

Official final decision:

- `handbook_decider`

Removed runtime roles:

- all bettor personas
- `bettor_handbook_advisor`
- `world_analyst`
- `hybrid_resonance_160`
- `hybrid_bridge_100`
- `llm_hybrid_panel`

## Execution Bindings

Execution defaults come from `backend/app/services/lottery/execution_config.yaml`.

The system resolves bindings in this order:

1. role default
2. group override
3. agent override
4. session `execution_overrides`

Rules:

- the UI selects `profile_id`
- UI overrides apply to the current session only
- YAML remains the source of persistent defaults
- no adaptive provider or model selection is used

Current Local/no-MCP runtime can enforce per-agent bindings.
Letta currently mirrors binding metadata only.

## Signal Boards

The canonical market surface is `SignalBoard`.

Generators may still emit `StrategyPrediction`, but runtime adapts them into boards before the market stage.

Boards carry at least:

- number scores
- structure scores
- play-size scores
- crowding penalties
- payout surrogates
- exclusions
- evidence refs
- confidence
- rationale

## Handbook Alignment

The runtime now separates:

- draw signal
- anti-crowding
- payout surrogate
- pattern risk

Handbook penalties include:

- arithmetic progression
- symmetry
- geometric pattern
- prior-winning-copy
- shifted-winning-copy
- hot/cold narrative
- omission chasing
- beautiful math pattern

These features are filters and value surrogates, not “more likely to draw” claims.

## Shared Memory Blocks

Current Letta shared blocks:

- `current_issue`
- `visible_draw_history_digest`
- `market_board`
- `social_feed`
- `purchase_board`
- `handbook_principles`
- `final_decision_constraints`
- `recent_outcomes`
- `report_digest`
- `rule_digest`
- `purchase_budget`

State machine logic stays in `world_v2_runtime`. Shared blocks only carry current-issue context.

## Game Kernel

Happy8 currently runs through:

- `games/base.py`
- `games/happy8/definition.py`
- `games/happy8/features.py`

This layer owns:

- selection validation
- plan expansion
- pricing
- settlement
- feature extraction

## Result Lines

Two result lines are explicit:

- official prediction line: `handbook_decider`
- purchase ROI line: `purchase_chair`

`latest_purchase_plan` means purchase recommendation only. It is not the official final prediction.

## Reports

Each run still writes a timestamped run report.

Per settled issue the system also writes:

- `reports/lottery-issue-ledger.json`
- `reports/lottery-issue-ledger.md`
- `reports/issues/issue_<suffix>_report.json`
- `reports/issues/issue_<suffix>_report.md`

Example:

- `reports/issues/issue_064_report.json`
- `reports/issues/issue_064_report.md`

Each per-issue report uses six fixed sections:

1. `本期背景`
2. `原始信号`
3. `社交过程`
4. `购买方案对比`
5. `最终决策`
6. `开奖后复盘`

## Kuzu Runtime Use

Kuzu is kept as an analysis substrate.

Current rules:

- workspace graph is synced for prediction context
- runtime projection is dirty-flagged
- projection flush happens at round close, not after every phase
- CSV import no longer writes headers into copied payloads

## Result Cache

Heavy agent outputs are cached by:

- `target_issue`
- `agent_id`
- `visible_history_hash`
- `prompt_hash`
- `config_hash`

This cache is used for social, judge, `purchase_chair`, and `handbook_decider`.

## no-MCP Development

`world_v2_market` can run without MCP.

Key pieces:

- env switch: `LOTTERY_WORLD_ALLOW_NO_MCP=true`
- direct local client: `LocalWorldClient`
- readiness branch: `world_runtime_readiness.py`

MCP still adds tools, but it is not required to start the runtime.

## API Example

```powershell
$body = @{
  strategy_ids = @("cold_rule", "hot_rule")
  pick_size = 5
  issue_parallelism = 1
  agent_dialogue_enabled = $true
  agent_dialogue_rounds = 5
  live_interview_enabled = $false
  visible_through_period = "2026063"
  execution_overrides = @{
    group = @{
      social = "social_fast_json"
    }
    agent = @{
      handbook_decider = "decision_default"
    }
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:5001/api/lottery/world/advance" `
  -ContentType "application/json" `
  -Body $body
```

## Local Dev

Backend:

```powershell
cd backend
python -m flask --app app run --debug --port 5001
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```
