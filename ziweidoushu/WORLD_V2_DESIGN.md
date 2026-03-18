# World V2 Design

## Goal

Keep `world_v2_market`, but make the chain readable, stable, and fast enough for daily use.

Core principles:

- one visible-through period at a time
- settle before the next prediction
- generator stage isolated by group
- market stage aggregated in one place
- official final decision separated from purchase ROI validation

## Public Interaction

Public entry:

- `POST /api/lottery/world/advance`

Inputs:

- `visible_through_period`
- `agent_dialogue_rounds`

Removed:

- `/api/lottery/world/evolution`
- `iterations`

## Visible-Through Model

`visible_through_period` means the last issue agents are allowed to see.

Example:

- visible through `2026063`
  - generators and market roles can only read data up to `2026063`
  - the runtime predicts `2026064`
- visible through `2026064`
  - if `2026064` has actual draw data, the runtime settles and postmortems `2026064`
  - then it predicts `2026065`

## Phase Flow

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

## Generator Isolation

The generator stage is intentionally split by group.

Rules:

- data group generates its own boards
- metaphysics group generates its own boards
- hybrid group generates its own boards
- no group reads another group's current-round outputs during `generator_opening`

Current generator groups:

- `data`
  - `cold_50`
  - `miss_120`
  - `momentum_60`
  - `structure_90`
  - `recent_board_50`
- `metaphysics`
  - `metaphysics_fused_board`
- `hybrid`
  - `hybrid_fused_board`

This is isolation, not blindness.

Meaning:

- generation phase stays separated
- social / judge / purchase / final decider are where cross-group aggregation happens

## Market Aggregation

The market stage is the only place where boards converge.

Roles:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`
- `handbook_decider`

Responsibilities:

- social: amplify or warn about current boards
- judge: re-rank and compress market consensus
- purchase_chair: produce executable purchase recommendation
- handbook_decider: publish the official final prediction

## Shared Memory Model

Letta is used as a shared-memory orchestration layer, not as the business state machine.

Current shared blocks:

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

Read/write intent:

- dynamic current-issue state goes into shared blocks
- long handbook or rules content stays in prompt assets / passages
- phase transitions, settlement, and reports stay inside `world_v2_runtime`

## Social Layer Limits

The social roster stays small by design.

Rules:

- size stays within `1..6`
- each social role must have a distinct `social_mode`
- avoid many near-duplicate voices

Current social roles:

- `social_consensus_feed`
- `social_risk_feed`

## Kuzu Role

Kuzu is an analysis substrate, not a per-phase runtime burden.

Current use:

- workspace graph sync for prediction context
- runtime market projection at round close
- issue / influencer / faction / crowding analysis

Current performance rules:

- runtime projection is dirty-flagged
- do not re-project after every phase
- flush projection at prediction close or settlement close
- CSV import omits headers to avoid polluted graph rows

## Result Cache

Heavy agent outputs are cached with this key:

- `target_issue`
- `agent_id`
- `visible_history_hash`
- `prompt_hash`
- `config_hash`

Used for:

- social
- judge
- `purchase_chair`
- `handbook_decider`

## Reporting

The system writes:

- timestamped run report
- cumulative issue ledger
- fixed per-issue reports

Per-issue report naming:

- `issue_064_report.json`
- `issue_064_report.md`

Per-issue report sections are fixed:

1. `本期背景`
2. `原始信号`
3. `社交过程`
4. `购买方案对比`
5. `最终决策`
6. `开奖后复盘`

## UI Principles

The inspector is primary. The graph is secondary.

The user should be able to see, without guessing:

- current visible-through issue
- current predicted issue
- current phase and actor
- generator boards
- market discussion
- purchase recommendation
- official final decision
- latest review
- issue ledger
