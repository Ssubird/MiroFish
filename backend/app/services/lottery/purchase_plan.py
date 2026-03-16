"""Purchase-plan generation and replay for Happy 8."""

from __future__ import annotations

from dataclasses import dataclass

from ...config import Config
from .objective import ticket_payout
from .performance_summary import performance_weight, rolling_strategy_performance, trusted_strategy_ids
from .purchase_discussion import PurchaseDiscussionService
from .purchase_helpers import signal_rows, trusted_rows
from .purchase_structures import TicketStructure, deterministic_tickets, planner_structure
from .research_types import WindowBacktest


PRIMARY_SELECTION_SIZE = 5
PLAN_BUDGET_YUAN = 50
TICKET_COST_YUAN = 2
MAX_TICKETS = PLAN_BUDGET_YUAN // TICKET_COST_YUAN
POOL_SIZE = 9
CORE_BONUS = 3.0
HEDGE_BONUS = 1.4
AVOID_PENALTY = 2.5
POSITION_BONUS_BASE = 0.35
TRUSTED_STRATEGY_BONUS = 1.2
TRUSTED_LIMIT = 6


@dataclass(frozen=True)
class PurchasePlanRequest:
    context: object
    pending_predictions: dict[str, object]
    strategies: dict[str, object]
    performance: dict[str, dict[str, object]]
    window_backtest: WindowBacktest
    pick_size: int
    ensemble_numbers: tuple[int, ...] = ()
    coordination_trace: tuple[dict[str, object], ...] = ()
    alternate_numbers: tuple[int, ...] = ()


class PurchasePlanService:
    """Build one pending purchase plan and replay it on the validation window."""

    def __init__(self, discussion_service: PurchaseDiscussionService | None = None):
        self.discussion_service = discussion_service or PurchaseDiscussionService(
            budget_yuan=PLAN_BUDGET_YUAN,
            ticket_cost_yuan=TICKET_COST_YUAN,
            max_tickets=MAX_TICKETS,
        )

    def build(self, request: PurchasePlanRequest) -> dict[str, object]:
        history = self._historical_backtest(request)
        if request.pick_size != PRIMARY_SELECTION_SIZE:
            return self._unsupported_plan(history, request)
        if not Config.LLM_API_KEY:
            return self._skipped_plan(history, request, "LLM_API_KEY is not configured.")
        if not self._has_llm_predictions(request.pending_predictions):
            return self._skipped_plan(history, request, "No LLM strategy is enabled for purchase discussion.")
        fallback_trusted = trusted_strategy_ids(request.performance, list(request.pending_predictions.keys()), TRUSTED_LIMIT)
        discussion = self.discussion_service.build(request, fallback_trusted)
        planner = discussion["planner"]
        try:
            structure = planner_structure(planner, request.pick_size, MAX_TICKETS)
        except ValueError as exc:
            return self._invalid_plan(history, request, planner, discussion, str(exc))
        tickets = self._ticket_rows(structure.tickets)
        return {
            "status": "ready",
            "game": "Happy 8",
            "budget_yuan": PLAN_BUDGET_YUAN,
            "ticket_cost_yuan": TICKET_COST_YUAN,
            "ticket_count": len(tickets),
            "total_cost_yuan": len(tickets) * TICKET_COST_YUAN,
            "primary_prediction": list(request.ensemble_numbers),
            "alternate_numbers": list(request.alternate_numbers),
            "signal_board": signal_rows(request.pending_predictions, request.performance),
            "trusted_strategies": trusted_rows(request.pending_predictions, request.performance, planner["trusted_strategy_ids"]),
            "discussion_agents": discussion["discussion_agents"],
            "discussion_trace": discussion["discussion_trace"],
            "planner": planner,
            "plan_type": structure.plan_type,
            "plan_structure": self._structure_payload(structure),
            "tickets": tickets,
            "historical_backtest": history,
        }

    def _historical_backtest(self, request: PurchasePlanRequest) -> dict[str, object]:
        issues = [self._historical_issue(request, index) for index in range(len(request.window_backtest.issue_replays))]
        total_cost = sum(int(item["cost"]) for item in issues)
        total_payout = sum(int(item["payout"]) for item in issues)
        return {
            "issues": len(issues),
            "total_cost": total_cost,
            "total_payout": total_payout,
            "net_profit": total_payout - total_cost,
            "roi": round((total_payout - total_cost) / total_cost, 4) if total_cost else 0.0,
            "winning_issues": len([item for item in issues if item["payout"] > 0]),
            "hit_distribution": self._hit_distribution(issues),
            "recent_issue_profit": issues[-5:],
            "method": "rolling replay with past-only trusted-strategy weighting and deterministic ticket expansion",
        }

    def _historical_issue(self, request: PurchasePlanRequest, issue_index: int) -> dict[str, object]:
        replay = request.window_backtest.issue_replays[issue_index]
        performance = rolling_strategy_performance(request.window_backtest.issue_results, request.strategies, issue_index)
        trusted_ids = trusted_strategy_ids(performance, list(replay.predictions.keys()), TRUSTED_LIMIT)
        scores = self._number_scores(replay.predictions, performance, trusted_ids, None)
        structure = deterministic_tickets(scores, [], request.pick_size, POOL_SIZE, MAX_TICKETS)
        payout = sum(self._ticket_payout(ticket, replay.target_draw.numbers) for ticket in structure.tickets)
        cost = len(structure.tickets) * TICKET_COST_YUAN
        return {
            "period": replay.target_draw.period,
            "trusted_strategy_ids": trusted_ids,
            "plan_type": structure.plan_type,
            "payout": payout,
            "cost": cost,
            "profit": payout - cost,
        }

    def _number_scores(
        self,
        predictions: dict[str, object],
        performance: dict[str, dict[str, object]],
        trusted_ids: list[str],
        planner: dict[str, object] | None,
    ) -> dict[int, float]:
        scores = {number: 0.0 for number in range(1, 81)}
        trusted = set(trusted_ids)
        for strategy_id, prediction in predictions.items():
            weight = performance_weight(performance, strategy_id)
            if strategy_id in trusted:
                weight += TRUSTED_STRATEGY_BONUS
            for index, number in enumerate(prediction.numbers):
                scores[number] += weight + POSITION_BONUS_BASE * (len(prediction.numbers) - index)
        if planner:
            self._apply_number_bonus(scores, planner.get("core_numbers", []), CORE_BONUS)
            self._apply_number_bonus(scores, planner.get("hedge_numbers", []), HEDGE_BONUS)
            self._apply_number_bonus(scores, planner.get("avoid_numbers", []), -AVOID_PENALTY)
            self._apply_number_bonus(scores, planner.get("primary_ticket", []), CORE_BONUS * 0.8)
        return scores

    def _apply_number_bonus(self, scores: dict[int, float], numbers: list[int], bonus: float) -> None:
        for number in numbers:
            scores[number] += bonus

    def _ticket_rows(self, tickets: tuple[tuple[int, ...], ...]) -> list[dict[str, object]]:
        return [
            {"index": index, "numbers": list(ticket), "unit_cost_yuan": TICKET_COST_YUAN}
            for index, ticket in enumerate(tickets, start=1)
        ]

    def _ticket_payout(self, ticket: tuple[int, ...], actual_numbers: tuple[int, ...]) -> int:
        hits = len(set(ticket) & set(actual_numbers))
        return ticket_payout(PRIMARY_SELECTION_SIZE, hits)

    def _structure_payload(self, structure: TicketStructure) -> dict[str, object]:
        payload = dict(structure.summary)
        if structure.tickets and structure.plan_type != "portfolio":
            payload["primary_ticket"] = list(structure.tickets[0])
        return payload

    def _has_llm_predictions(self, predictions: dict[str, object]) -> bool:
        return any(getattr(prediction, "kind", "") == "llm" for prediction in predictions.values())

    def _hit_distribution(self, issues: list[dict[str, object]]) -> dict[str, int]:
        return {
            "positive_profit": len([item for item in issues if item["profit"] > 0]),
            "break_even_or_better": len([item for item in issues if item["profit"] >= 0]),
        }

    def _plan_context(self, request: PurchasePlanRequest) -> dict[str, object]:
        return {
            "game": "Happy 8",
            "budget_yuan": PLAN_BUDGET_YUAN,
            "ticket_cost_yuan": TICKET_COST_YUAN,
            "primary_prediction": list(request.ensemble_numbers),
            "alternate_numbers": list(request.alternate_numbers),
        }

    def _unsupported_plan(self, history: dict[str, object], request: PurchasePlanRequest) -> dict[str, object]:
        return {
            "status": "unsupported",
            "reason": f"Purchase planning expects a 5-number primary prediction, got pick_size={request.pick_size}.",
            **self._plan_context(request),
            "historical_backtest": history,
        }

    def _skipped_plan(self, history: dict[str, object], request: PurchasePlanRequest, reason: str) -> dict[str, object]:
        return {
            "status": "skipped",
            "reason": reason,
            **self._plan_context(request),
            "historical_backtest": history,
        }

    def _invalid_plan(
        self,
        history: dict[str, object],
        request: PurchasePlanRequest,
        planner: dict[str, object],
        discussion: dict[str, object],
        reason: str,
    ) -> dict[str, object]:
        return {
            "status": "invalid",
            "reason": reason,
            **self._plan_context(request),
            "planner": planner,
            "discussion_agents": discussion["discussion_agents"],
            "discussion_trace": discussion["discussion_trace"],
            "historical_backtest": history,
        }
