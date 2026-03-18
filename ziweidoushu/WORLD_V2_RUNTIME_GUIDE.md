# world_v2_market Runtime Guide

## Current State

`world_v2_market` is the active mainline runtime.

It now supports:

- normal visible-through progression
- settle-before-next-predict workflow
- no-MCP local development baseline
- Letta shared memory blocks for current-issue collaboration
- Kuzu runtime projection with dirty-flagged flush

## Running Modes

Current runtime paths:

- `Letta + MCP`
  - full tool-enabled mode
- `Letta + no-MCP`
  - valid development baseline
- `LocalWorldClient`
  - local direct-call fallback for explicit no-MCP mode

Important switch:

- `LOTTERY_WORLD_ALLOW_NO_MCP=true`

Important files:

- `backend/app/api/lottery.py`
- `backend/app/services/lottery/research_service.py`
- `backend/app/services/lottery/world_runtime_readiness.py`
- `backend/app/services/lottery/local_world_client.py`

## Main Runtime Semantics

The UI and API both operate on `visible_through_period`.

Example:

- choose `2026063`
  - agents only see data up to `2026063`
  - runtime predicts `2026064`
- choose `2026064`
  - if `2026064` actual numbers exist, runtime settles `2026064`
  - then runtime predicts `2026065`

## Runtime Phases

Prediction:

1. `generator_opening`
2. `social_propagation`
3. `market_rerank`
4. `plan_synthesis`
5. `handbook_final_decision`
6. `await_result`

Settlement:

1. `settlement`
2. `postmortem`

## Agent Flow

Generator stage:

- `data`
- `metaphysics`
- `hybrid`

These groups generate independently during `generator_opening`.

Aggregation stage:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`
- `handbook_decider`

This is the only place current-round cross-group convergence happens.

## Shared Memory Blocks

Current blocks:

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

Meaning:

- shared blocks carry current issue context
- long documents still go through prompt assets / passages
- runtime state transitions stay in `world_v2_runtime`

## Kuzu Position

Kuzu is still important, but it should not dominate every phase.

Current design:

- sync workspace graph for prediction context
- use runtime projection for market analysis
- flush runtime projection only when needed

Current performance fixes:

- projection is dirty-flagged
- do not project after every phase
- flush at prediction close and settlement close
- CSV import omits headers to avoid polluted graph nodes

## Result Cache

Current cache key:

- `target_issue`
- `agent_id`
- `visible_history_hash`
- `prompt_hash`
- `config_hash`

Current cached roles:

- social
- judge
- `purchase_chair`
- `handbook_decider`

## Reports

Generated outputs include:

- run report
- issue ledger
- fixed per-issue reports

Per-issue report naming:

- `issue_064_report.json`
- `issue_064_report.md`

Per-issue report sections:

1. `本期背景`
2. `原始信号`
3. `社交过程`
4. `购买方案对比`
5. `最终决策`
6. `开奖后复盘`
