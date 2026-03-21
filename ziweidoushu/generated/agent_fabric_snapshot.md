# Agent Fabric Snapshot

## Single Agent Input Sources

| Agent | Role | Group | Profile | Phases | Shared Blocks | Bound Documents |
| --- | --- | --- | --- | --- | --- | --- |
| purchase_chair | purchase | purchase | purchase_default | plan_synthesis, final_decision | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, final_decision_constraints, report_digest, rule_digest, purchase_budget, handbook_principles | prompt.md, data/draws/keno8_predict_data.json, lottery_handbook_deep_notes.md |
| purchase_coverage_builder | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, final_decision_constraints, report_digest, rule_digest, purchase_budget | - |
| purchase_value_guard | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, final_decision_constraints, report_digest, rule_digest, purchase_budget | - |
| purchase_ziwei_conviction | purchase | purchase | purchase_default | plan_synthesis | current_issue, visible_draw_history_digest, market_board, social_feed, purchase_board, final_decision_constraints, report_digest, rule_digest, purchase_budget, handbook_principles | lottery_handbook_deep_notes.md |
| social_consensus_feed | social | social | social_default | social_propagation | current_issue, visible_draw_history_digest, market_board, social_feed, report_digest, rule_digest, purchase_budget | - |

## Phase Group Agent Matrix

| Phase | Active Groups | Agent IDs |
| --- | --- | --- |
| social_propagation | social | social_consensus_feed |
| plan_synthesis | purchase | purchase_chair, purchase_coverage_builder, purchase_value_guard, purchase_ziwei_conviction |
| final_decision | purchase | purchase_chair |

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
