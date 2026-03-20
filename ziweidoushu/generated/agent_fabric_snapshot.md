# Agent Fabric Snapshot

## Single Agent Input Sources

| Agent | Role | Group | Profile | Phases | Shared Blocks | Bound Documents |
| --- | --- | --- | --- | --- | --- | --- |
| consensus_judge | judge | judge | judge_default | market_rerank | current_issue, visible_draw_history_digest, market_board, social_feed, handbook_principles, report_digest, rule_digest, purchase_budget | lottery_handbook_deep_notes.md |
| purchase_chair | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, handbook_principles, report_digest, rule_digest, purchase_budget, final_decision_constraints | prompt.md, data/draws/keno8_predict_data.json, lottery_handbook_deep_notes.md |
| purchase_coverage_builder | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, handbook_principles, report_digest, rule_digest, purchase_budget | lottery_handbook_deep_notes.md |
| purchase_value_guard | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, handbook_principles, report_digest, rule_digest, purchase_budget | lottery_handbook_deep_notes.md |
| purchase_ziwei_conviction | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, handbook_principles, report_digest, rule_digest, purchase_budget | lottery_handbook_deep_notes.md |
| social_consensus_feed | social | social | social_default | social_propagation | current_issue, visible_draw_history_digest, market_board, social_feed, handbook_principles, report_digest, rule_digest, purchase_budget | lottery_handbook_deep_notes.md |

## Phase Group Agent Matrix

| Phase | Active Groups | Agent IDs |
| --- | --- | --- |
| social_propagation | social | social_consensus_feed |
| market_rerank | judge | consensus_judge |
| plan_synthesis | purchase | purchase_chair, purchase_coverage_builder, purchase_value_guard, purchase_ziwei_conviction |
| handbook_final_decision | decision | - |

## Data Group Inventory

| Strategy | Group | Kind | Required History |
| --- | --- | --- | --- |
| cold_50 | data | rule | 50 |
| miss_120 | data | rule | 120 |
| momentum_60 | data | rule | 60 |
| structure_90 | data | rule | 90 |
| recent_board_50 | data | rule | 50 |
| metaphysics_fused_board | metaphysics | rule | 240 |
| hybrid_fused_board | hybrid | rule | 160 |
| full_context_ziwei | metaphysics | llm | 120 |
