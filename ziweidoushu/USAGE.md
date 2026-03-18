# Lottery World Usage

## Current Runtime

- Primary runtime: `world_v2_market`
- Public action: `POST /api/lottery/world/advance`
- Removed: `/api/lottery/world/evolution`
- Removed: `iterations`
- Kept: `agent_dialogue_rounds`
- Frontend discussion rounds max: `5`

## Visible-Through Workflow

The period selector now means `visible_through_period`.

Rules:

- Select `2026063`
  - visible data ends at `2026063`
  - the system predicts `2026064`
  - `2026064` actual numbers must stay hidden
- Select `2026064` next time
  - if `2026064` actual data is already present, the system first settles and postmortems `2026064`
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

## Shared Memory Blocks

The current Letta shared blocks are:

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

## Result Lines

Two lines are now explicit:

- Official prediction line: `handbook_decider`
- Purchase ROI line: `purchase_chair`

`latest_purchase_plan` means purchase recommendation only. It is not the official final prediction.

## Reports

Each run still writes a timestamped run report.

Per settled issue the system now also writes:

- ledger
  - `reports/lottery-issue-ledger.json`
  - `reports/lottery-issue-ledger.md`
- fixed per-issue reports
  - `reports/issues/issue_<suffix>_report.json`
  - `reports/issues/issue_<suffix>_report.md`

Example:

- `reports/issues/issue_064_report.json`
- `reports/issues/issue_064_report.md`

Each per-issue report is fixed to six sections:

1. `本期背景`
2. `原始信号`
3. `社交过程`
4. `购买方案对比`
5. `最终决策`
6. `开奖后复盘`

## Kuzu Runtime Use

Kuzu is kept as an analysis substrate, not a per-phase hard dependency.

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

Important pieces:

- env switch: `LOTTERY_WORLD_ALLOW_NO_MCP=true`
- local direct client: `LocalWorldClient`
- readiness branch: `world_runtime_readiness.py`

MCP still adds tools, but it is no longer a hard start-up requirement.

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
} | ConvertTo-Json

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
