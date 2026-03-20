# World V2.5 Design

## Goal

Keep `world_v2_market`, but upgrade it into a clearer execution market:

- explicit issue progression
- explicit per-agent execution binding
- canonical signal boards
- handbook-aligned anti-crowding logic
- Happy8-first game kernel boundary

## Runtime Entry

Public endpoints:

- `POST /api/lottery/world/prepare`
- `POST /api/lottery/world/advance`
- `GET /api/lottery/execution/registry`

Core inputs:

- `visible_through_period`
- `agent_dialogue_rounds`
- `execution_overrides`

Removed:

- `/api/lottery/world/evolution`
- `iterations`

## Visible-Through Model

`visible_through_period` means the last issue agents may see.

Example:

- visible through `2026063`
  - visible data ends at `2026063`
  - the runtime predicts `2026064`
- visible through `2026064`
  - if `2026064` draw data already exists, the runtime settles and postmortems `2026064`
  - then it predicts `2026065`

Repeated clicks on the same visible-through issue with unchanged draw data do not create duplicate predictions or duplicate settlement records.

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

Generation is isolated by group.

Rules:

- data, metaphysics, and hybrid groups generate independently
- groups do not read each other's same-round outputs during `generator_opening`
- cross-group aggregation begins only in the market stage

Current groups:

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

## Market Roles

Boards converge only in the market stage.

Roles:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`
- `handbook_decider`

Responsibilities:

- social roles amplify, question, and warn about signal boards
- judge re-ranks and compresses the market picture
- purchase chair produces executable purchase structures
- handbook decider publishes the official final decision

## Execution Fabric

Execution binding is explicit. There is no adaptive provider or model selection.

Persistent defaults come from `execution_config.yaml`:

- `providers`
- `models`
- `profiles`
- `role_defaults`
- `group_overrides`
- `agent_overrides`
- `decision_weights`
- `happy8_feature_profile`

Binding precedence:

1. role default
2. group override
3. agent override
4. session `execution_overrides`

Rules:

- the UI selects `profile_id`, not raw provider/model text
- the UI only writes session-scoped overrides
- session overrides never rewrite YAML
- resolved bindings are stored in session payloads, reports, and execution logs

Current runtime scope:

- Local/no-MCP execution enforces per-agent provider/model binding
- Letta currently carries aligned binding metadata only
- Letta does not yet execute different providers per agent in this phase

## Signal Market Surface

Canonical market truth is `SignalBoard`.

Each board may include:

- `number_scores`
- `structure_scores`
- `play_size_scores`
- `crowding_penalties`
- `payout_surrogates`
- `exclusions`
- `evidence_refs`
- `confidence`
- `rationale`

Compatibility rule:

- old generators may still emit `StrategyPrediction`
- runtime adapts generator output into `SignalBoard` before the market stage
- reports and payloads should prefer `signal_boards`

## Handbook-Aligned Scoring

The system now separates draw signals from crowding and payout concerns.

Main scoring surfaces:

- `draw_signal`
- `anti_crowding`
- `payout_surrogate`
- `pattern_risk`

Anti-crowding penalties include:

- arithmetic progression risk
- symmetry risk
- geometric pattern risk
- prior-winning-copy risk
- shifted-winning-copy risk
- hot/cold narrative risk
- omission-chasing risk
- beautiful-math-pattern risk

Interpretation rule:

- AC, sum, edge counts, and cluster counts are treated as filters or payout surrogates
- they are not described as oracle-like predictors of the next draw

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

- current-issue dynamic state goes into shared blocks
- long handbook text stays in prompt assets
- phase transitions, settlement, reports, and issue truth stay inside `world_v2_runtime`

## Game Kernel

Happy8 now runs behind a game-kernel boundary.

Current layout:

- `games/base.py`
- `games/happy8/definition.py`
- `games/happy8/features.py`

Current `GameDefinition` responsibilities:

- validate selection
- expand plan
- price plan
- settle plan
- extract features

Runtime rule:

- `world_v2_runtime` depends on `game_id + play_mode + GameDefinition`
- Happy8 constants, pricing rules, and settlement rules stay inside the game layer

## Kuzu Role

Kuzu is an analysis substrate, not a per-phase runtime burden.

Current use:

- workspace graph sync for prediction context
- runtime market projection at round close
- issue, influencer, faction, crowding, and similarity analysis

Current performance rules:

- runtime projection is dirty-flagged
- projection is not re-run after every phase
- projection flushes at prediction close or settlement close
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

The user should be able to see:

- current visible-through issue
- current predicted issue
- current phase and actor
- current execution bindings by group and agent
- generator boards
- market discussion
- purchase recommendation
- official final decision
- latest review
- issue ledger
