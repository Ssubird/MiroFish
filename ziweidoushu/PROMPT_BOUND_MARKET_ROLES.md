# Prompt-Bound Market Roles

This document explains how handbook-style prompt assets are bound inside the current `world_v2_market`.

## Current Bound Roles

The handbook file:

- `knowledge/prompts/lottery_handbook_deep_notes.md`

is currently bound to:

- `social_consensus_feed`
- `social_risk_feed`
- `consensus_judge`
- `purchase_chair`
- `handbook_decider`

It is intentionally not bound to generator roles.

## Why Generators Stay Unbound

Generator groups must stay raw and isolated during `generator_opening`.

That means:

- data boards should stay data-first
- metaphysics boards should stay metaphysics-first
- hybrid boards should stay hybrid-first
- final decision doctrine should not leak backward into board generation

## What Bound Roles Use the Handbook For

### Social Roles

Use the handbook as discussion doctrine.

Focus:

- crowding warnings
- market dilution risk
- suspiciously popular structures

### Judge Role

Use the handbook as rerank discipline.

Focus:

- whether consensus is too crowded
- whether a board is overfit to public-looking structure
- whether a market summary should be compressed or resisted

### purchase_chair

Uses the handbook as purchase-structure discipline.

Focus:

- budget fit
- executable structure
- anti-crowding purchase shape

### handbook_decider

Uses the handbook as the final official doctrine layer.

Focus:

- official final numbers
- alternate numbers
- why a market plan is accepted or rejected
- final risk note

## Injection Path

The current binding has two layers:

1. prompt asset passages during agent registration
2. current-issue shared blocks plus live prompts during the active round

Important code paths:

- `backend/app/services/lottery/market_role_registry.py`
- `backend/app/services/lottery/world_v2_runtime.py`

## Shared Blocks Used Together With Handbook Binding

The most important current blocks are:

- `market_board`
- `social_feed`
- `purchase_board`
- `handbook_principles`
- `final_decision_constraints`

This means the handbook is no longer just a static document attachment. It now works together with live current-round context.
