# world_v2_market Troubleshooting

## Quick Triage Order

Do not start by changing prompts.

Check in this order:

1. frontend status banner and readiness card
2. failing API request in Network
3. backend console traceback
4. session file under `.world_state/<session_id>/session.json`
5. only then inspect code

## Most Useful API Checks

Model list:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:5001/api/lottery/models"
```

Runtime readiness:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:5001/api/lottery/world/runtime-readiness"
```

Current world session:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:5001/api/lottery/world/current"
```

Advance one round:

```powershell
$body = @{
  strategy_ids = @("cold_rule", "hot_rule")
  pick_size = 5
  visible_through_period = "2026064"
  agent_dialogue_enabled = $true
  agent_dialogue_rounds = 5
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:5001/api/lottery/world/advance" `
  -ContentType "application/json" `
  -Body $body
```

## Session Files

Important files:

- `ziweidoushu/.world_state/current_session.txt`
- `ziweidoushu/.world_state/<session_id>/session.json`
- `ziweidoushu/.world_state/<session_id>/timeline.jsonl`
- `ziweidoushu/.world_state/<session_id>/result.json`

Most important fields in `session.json`:

- `status`
- `current_phase`
- `failed_phase`
- `error`
- `execution_log`
- `progress`
- `latest_prediction`
- `latest_review`

## Common Cases

### 1. Model list is empty

Check:

- `GET /api/lottery/models`
- `LLM_BASE_URL`
- `LLM_API_KEY`

This is not a Letta readiness problem first. It is usually the upstream LLM provider path.

### 2. Readiness says not ready

Check:

- `GET /api/lottery/world/runtime-readiness`
- `blocking_code`
- `blocking_message`
- `runtime_backend`

Common reasons:

- Letta not configured
- Letta unreachable
- no-MCP local mode missing `LLM_BASE_URL` or `LLM_API_KEY`
- current Letta environment not supporting stdio MCP

### 3. Advance fails before session creation

Usually this is:

- readiness/preflight block
- invalid request payload
- backend route mismatch

Check:

- failing request payload
- backend traceback
- whether backend process is the latest code

### 4. Advance creates session but quickly becomes `failed`

Check:

- `session.json.error`
- `session.json.execution_log`
- backend traceback

Then map the failure to the phase:

- `generator_opening`
- `social_propagation`
- `market_rerank`
- `plan_synthesis`
- `handbook_final_decision`
- `settlement`
- `postmortem`

### 5. Frontend shows no world result

Check backend state first:

- `session.status`
- `session.current_phase`
- `session.latest_prediction`
- `timeline.jsonl`

If backend never advanced, the graph/inspector being empty is only the result, not the root cause.

## Kuzu Checks

Current Kuzu expectations:

- workspace graph can sync
- runtime projection is flushed only at round close
- CSV import should not contain header rows

If Kuzu errors appear, check:

- `backend/app/services/lottery/kuzu_graph.py`
- `backend/app/services/lottery/kuzu_market_runtime.py`
- whether the workspace graph state exists before runtime projection reads it

## Shared Memory Checks

Current important blocks:

- `current_issue`
- `visible_draw_history_digest`
- `market_board`
- `social_feed`
- `purchase_board`
- `handbook_principles`
- `final_decision_constraints`

If a role looks blind, inspect the agent blocks and session shared memory first.

## Code Index

API:

- `backend/app/api/lottery.py`

Runtime selection and readiness:

- `backend/app/services/lottery/research_service.py`
- `backend/app/services/lottery/world_runtime_readiness.py`
- `backend/app/services/lottery/world_runtime_flags.py`

Main runtime:

- `backend/app/services/lottery/world_v2_runtime.py`
- `backend/app/services/lottery/world_v2_market.py`

Reports:

- `backend/app/services/lottery/report_writer.py`
- `backend/app/services/lottery/issue_report.py`
- `backend/app/services/lottery/issue_report_markdown.py`
