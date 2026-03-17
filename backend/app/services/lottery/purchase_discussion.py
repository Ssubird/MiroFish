"""Multi-agent discussion for purchase planning."""

from __future__ import annotations

from dataclasses import dataclass
import time

from ...utils.llm_client import LLMClient
from .agents.prompt_blocks import expert_interview_summary, prompt_summary, report_summary, world_summary
from .purchase_helpers import (
    coordination_block,
    performance_block,
    planner_payload,
    purchase_dialogue_block,
    purchase_proposal_block,
    signal_block,
    signal_rows,
    social_state_block,
)


MAX_PROPOSAL_TOKENS = 1400
MAX_DISCUSSION_TOKENS = 1400
MAX_SYNTHESIS_TOKENS = 1800
PURCHASE_DISCUSSION_ROUNDS = 2


@dataclass(frozen=True)
class PurchaseRole:
    role_id: str
    display_name: str
    mandate: str


PURCHASE_ROLES = (
    PurchaseRole("budget_guard", "LLM-Budget-Guard", "Protect the bankroll. Compare play sizes and avoid wasting the budget on lazy repeated singles."),
    PurchaseRole("coverage_builder", "LLM-Coverage-Builder", "Use the main 5 numbers and the 3 alternates to maximize structured coverage, including mixed portfolios."),
    PurchaseRole("upside_hunter", "LLM-Upside-Hunter", "Seek asymmetric upside across play sizes, structures, and concentrated conviction bets."),
)


class PurchaseDiscussionService:
    """Run proposal, discussion, and final synthesis for purchase planning."""

    def __init__(self, budget_yuan: int, ticket_cost_yuan: int, max_tickets: int):
        self.budget_yuan = budget_yuan
        self.ticket_cost_yuan = ticket_cost_yuan
        self.max_tickets = max_tickets

    def build(self, request, fallback_trusted_ids: list[str]) -> dict[str, object]:
        client = self._client(request)
        proposals = [self._proposal(role, request, client, fallback_trusted_ids) for role in PURCHASE_ROLES]
        discussion_trace = self._discussion_rounds(request, client, proposals, fallback_trusted_ids)
        planner = self._synthesis(request, client, proposals, discussion_trace, fallback_trusted_ids)
        return {
            "planner": planner,
            "discussion_agents": proposals,
            "discussion_trace": discussion_trace,
        }

    def _proposal(self, role: PurchaseRole, request, client: LLMClient, fallback_trusted_ids: list[str]) -> dict[str, object]:
        messages = self._proposal_messages(role, request)
        response = self._request_json(client, request, messages, MAX_PROPOSAL_TOKENS)
        return planner_payload(
            role.display_name,
            role.role_id,
            client.model,
            messages,
            response,
            request.pending_predictions,
            fallback_trusted_ids,
            request.pick_size,
        )

    def _discussion_rounds(
        self,
        request,
        client: LLMClient,
        proposals: list[dict[str, object]],
        fallback_trusted_ids: list[str],
    ) -> list[dict[str, object]]:
        rows = []
        for round_index in range(1, PURCHASE_DISCUSSION_ROUNDS + 1):
            rows.extend(self._run_round(round_index, request, client, proposals, fallback_trusted_ids))
        return rows

    def _run_round(
        self,
        round_index: int,
        request,
        client: LLMClient,
        proposals: list[dict[str, object]],
        fallback_trusted_ids: list[str],
    ) -> list[dict[str, object]]:
        notes = []
        for index, role in enumerate(PURCHASE_ROLES):
            updated = self._revise(role, proposals[index], proposals, request, client, round_index, fallback_trusted_ids)
            proposals[index] = updated
            notes.append(self._discussion_note(updated, round_index))
        return notes

    def _revise(
        self,
        role: PurchaseRole,
        own: dict[str, object],
        proposals: list[dict[str, object]],
        request,
        client: LLMClient,
        round_index: int,
        fallback_trusted_ids: list[str],
    ) -> dict[str, object]:
        messages = self._revision_messages(role, own, proposals, request, round_index)
        response = self._request_json(client, request, messages, MAX_DISCUSSION_TOKENS)
        updated = planner_payload(
            role.display_name,
            role.role_id,
            client.model,
            messages,
            response,
            request.pending_predictions,
            fallback_trusted_ids,
            request.pick_size,
        )
        return {**updated, "comment": updated.get("comment") or own.get("comment", "")}

    def _synthesis(
        self,
        request,
        client: LLMClient,
        proposals: list[dict[str, object]],
        discussion_trace: list[dict[str, object]],
        fallback_trusted_ids: list[str],
    ) -> dict[str, object]:
        messages = self._synthesis_messages(request, proposals, discussion_trace)
        response = self._request_json(client, request, messages, MAX_SYNTHESIS_TOKENS)
        return planner_payload(
            "LLM-Purchase-Chair",
            "purchase_chair",
            client.model,
            messages,
            response,
            request.pending_predictions,
            fallback_trusted_ids,
            request.pick_size,
        )

    def _proposal_messages(self, role: PurchaseRole, request) -> list[dict[str, str]]:
        lines = self._shared_lines(request)
        lines.extend(
            [
                f"Role: {role.display_name}",
                f"Mandate: {role.mandate}",
                "Return one concrete plan. You may use tickets, wheel, dan_tuo, or a mixed portfolio under budget.",
                self._plan_schema(),
            ]
        )
        return [self._system_message("Make an initial purchase proposal."), {"role": "user", "content": "\n".join(lines)}]

    def _revision_messages(self, role: PurchaseRole, own: dict[str, object], proposals: list[dict[str, object]], request, round_index: int) -> list[dict[str, str]]:
        peer_rows = [item for item in proposals if item.get("role_id") != role.role_id]
        lines = self._shared_lines(request)
        lines.extend(
            [
                f"Role: {role.display_name}",
                f"Mandate: {role.mandate}",
                f"Discussion Round: {round_index}",
                f"Your Current Proposal:\n{purchase_proposal_block([own])}",
                f"Peer Proposals:\n{purchase_proposal_block(peer_rows)}",
                "Reply after reading peers. You may keep or revise your plan, and you must add a direct comment.",
                self._discussion_schema(),
            ]
        )
        return [self._system_message("Debate the purchase plan with peers before revising."), {"role": "user", "content": "\n".join(lines)}]

    def _synthesis_messages(self, request, proposals: list[dict[str, object]], discussion_trace: list[dict[str, object]]) -> list[dict[str, str]]:
        lines = self._shared_lines(request)
        lines.extend(
            [
                "You are the chair of the purchase committee.",
                f"Final Proposals:\n{purchase_proposal_block(proposals)}",
                f"Discussion Trace:\n{purchase_dialogue_block(discussion_trace)}",
                "Choose or synthesize the strongest executable plan under the fixed budget. Mixed portfolios are allowed.",
                self._plan_schema(),
            ]
        )
        return [self._system_message("Synthesize a final purchase plan from the committee discussion."), {"role": "user", "content": "\n".join(lines)}]

    def _shared_lines(self, request) -> list[str]:
        pick = getattr(request, "pick_size", 5)
        return [
            f"Target Period: {request.context.target_draw.period}",
            f"Budget: {self.budget_yuan} yuan; unit ticket cost: {self.ticket_cost_yuan} yuan; max tickets: {self.max_tickets}",
            f"Primary Prediction ({pick} numbers): {list(request.ensemble_numbers)}",
            f"Alternate Numbers: {list(request.alternate_numbers)}",
            "The purchase committee may expand the primary prediction into tickets / wheel / dan_tuo / portfolio.",
            f"Use the committee discussion to decide how to spend the {self.budget_yuan} yuan budget.",
            "You may mix multiple play sizes (1-10) and structures as long as total cost stays within budget.",
            "Backtest Performance:",
            performance_block(request.performance),
            "World State:",
            world_summary(request.context),
            "Prompt Asset:",
            prompt_summary(request.context, "purchase"),
            "Expert Interviews:",
            expert_interview_summary(request.context),
            "Current Candidate Board:",
            signal_block(signal_rows(request.pending_predictions, request.performance)),
            "External Reports:",
            report_summary(request.context),
            "Agent Coordination Summary:",
            coordination_block(request.coordination_trace),
            "Persistent Social State:",
            social_state_block(getattr(request.context, "social_state", {})),
        ]

    def _request_json(self, client: LLMClient, request, messages: list[dict[str, str]], max_tokens: int) -> dict[str, object]:
        if request.context.llm_request_delay_ms > 0:
            time.sleep(request.context.llm_request_delay_ms / 1000)
        return client.chat_json(messages, temperature=0.2, max_tokens=max_tokens)

    def _client(self, request) -> LLMClient:
        return LLMClient(
            model=request.context.llm_model_name or None,
            retry_count=request.context.llm_retry_count,
            retry_backoff_ms=request.context.llm_retry_backoff_ms,
        )

    def _system_message(self, task: str) -> dict[str, str]:
        return {
            "role": "system",
            "content": (
                "You are a Happy 8 purchase-planning agent. "
                "Stay within budget, reason from evidence, and make an explicit structured plan. "
                f"{task}"
            ),
        }

    def _plan_schema(self) -> str:
        return (
            'Return JSON only: {"plan_style":"...", "plan_type":"tickets|wheel|dan_tuo|portfolio", '
            '"play_size":5, "play_size_review":{"<size>":"<reason>"}, '
            '"chosen_edge":"...", "trusted_strategy_ids":["..."], "tickets":[[...]], '
            '"wheel_numbers":[...], "banker_numbers":[...], "drag_numbers":[...], '
            '"portfolio_legs":[{"plan_type":"tickets|wheel|dan_tuo","play_size":5,"tickets":[[...]],'
            '"wheel_numbers":[...],"banker_numbers":[...],"drag_numbers":[...],"primary_ticket":[...],"comment":"...","rationale":"..."}], '
            '"primary_ticket":[...], "core_numbers":[...], "hedge_numbers":[...], "avoid_numbers":[...], '
            '"focus":["..."], "rationale":"..."}'
        )

    def _discussion_schema(self) -> str:
        return (
            'Return JSON only: {"comment":"...", "support_role_ids":["..."], "plan_style":"...", '
            '"plan_type":"tickets|wheel|dan_tuo|portfolio", "play_size":5, '
            '"play_size_review":{"<size>":"<reason>"}, "chosen_edge":"...", '
            '"trusted_strategy_ids":["..."], "tickets":[[...]], "wheel_numbers":[...], '
            '"banker_numbers":[...], "drag_numbers":[...], "portfolio_legs":[{"plan_type":"tickets|wheel|dan_tuo","play_size":5}], '
            '"primary_ticket":[...], "core_numbers":[...], "hedge_numbers":[...], "avoid_numbers":[...], "focus":["..."], "rationale":"..."}'
        )

    def _discussion_note(self, proposal: dict[str, object], round_index: int) -> dict[str, object]:
        return {
            "round": round_index,
            "role_id": proposal.get("role_id"),
            "display_name": proposal.get("display_name"),
            "comment": proposal.get("comment", ""),
            "support_role_ids": list(proposal.get("support_role_ids", [])),
            "plan_type": proposal.get("plan_type"),
            "primary_ticket": list(proposal.get("primary_ticket", [])),
            "wheel_numbers": list(proposal.get("wheel_numbers", [])),
            "banker_numbers": list(proposal.get("banker_numbers", [])),
            "drag_numbers": list(proposal.get("drag_numbers", [])),
        }
