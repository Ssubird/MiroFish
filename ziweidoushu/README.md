# ZiweiDoushu Workspace

This workspace holds the lottery-specific data, handbook documents, and design notes used by the current `world_v2_market`.

## Layout

- `data/draws/`
  - structured Keno8 draw data
- `data/charts/`
  - optional chart and profile files
- `knowledge/learn/`
  - reference material
- `knowledge/prompts/`
  - prompt and handbook documents
- `reports/`
  - generated run reports, ledger, and per-issue reports

## Core Documents

- `USAGE.md`
  - day-to-day runtime usage
- `WORLD_V2_DESIGN.md`
  - current architecture and boundaries
- `AGENT_ARCHITECTURE.md`
  - role layers and final authority
- `WORLD_V2_RUNTIME_GUIDE.md`
  - runtime, no-MCP, Letta, Kuzu notes
- `PROMPT_BOUND_MARKET_ROLES.md`
  - handbook binding rules

## Current Runtime Summary

- runtime: `world_v2_market`
- progression input: `visible_through_period`
- discussion rounds: supported, max `5`
- official final prediction: `handbook_decider`
- purchase ROI line: `purchase_chair`
- per-issue reports: `issue_<suffix>_report.json` and `issue_<suffix>_report.md`
