# Agent Architecture

## Runtime Scope

This document describes the current `world_v2_market` runtime only.

## Layer 1: Generator Layer

Generators are isolated board producers.

Rules:

- they generate during `generator_opening`
- they do not read other groups' current-round outputs
- they do not own final authority
- they only meet other groups in later market phases

### Data Group

- `cold_50`
- `miss_120`
- `momentum_60`
- `structure_90`
- `recent_board_50`

### Metaphysics Group

- `metaphysics_fused_board`

### Hybrid Group

- `hybrid_fused_board`

## Layer 2: Market Discussion Layer

These roles read generator boards after generation is complete.

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`

Responsibilities:

- quote and amplify signals
- warn about crowding and risk
- re-rank the market view into a usable board

## Layer 3: Purchase Recommendation Layer

This role owns executable purchase planning only.

- `purchase_chair`

Output focus:

- plan type
- play size
- budget fit
- ticket structure
- purchase rationale

It is not the official final decision.

## Layer 4: Official Final Decision Layer

This is the only official final authority.

- `handbook_decider`

It reads:

- all generator boards
- social discussion
- judge boards
- purchase recommendation
- latest review
- issue ledger
- `knowledge/prompts/lottery_handbook_deep_notes.md`

It outputs:

- official final numbers
- alternate numbers
- adopted groups
- whether `purchase_chair` was accepted
- rationale
- risk note

## Prompt Binding

The handbook prompt is bound to:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`
- `handbook_decider`

The generator layer is intentionally kept free of handbook binding to avoid contaminating raw board generation.

## Shared Memory

Current shared blocks available to market roles:

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

## Removed Roles

These roles are not part of the current runtime:

- all bettor personas
- `bettor_handbook_advisor`
- `world_analyst`
- `hybrid_resonance_160`
- `hybrid_bridge_100`
- `llm_hybrid_panel`
