"""Helpers for the persistent Letta-backed lottery world."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from .constants import ALTERNATE_NUMBER_COUNT
from .happy8_rules import ALLOWED_PLAY_SIZES, play_rule_lines
from .models import PredictionContext, StrategyPrediction


WORLD_GOAL = "Keep a persistent prediction world, let agents debate, and maximize Happy 8 hit rate plus bankroll efficiency."
MANUAL_REPORT_DIGEST = (
    "prediction_report.md is manual-reference-only. It never enters runtime, grounding, agents, or the purchase committee."
)
NO_SETTLED_OUTCOME = "No settled world rounds yet."
NO_RULE_DIGEST = "No deterministic rule digest yet."
ISSUE_BRIEF_LIMIT = 2200
DIGEST_LIMIT = 900
PROMPT_PASSAGE_LIMIT = 1200
PROMPT_PASSAGE_COUNT = 1
PURCHASE_ROLES = (
    (
        "budget_guard",
        "LLM-Budget-Guard",
        "Protect the bankroll. Compare play sizes 3/4/5/6 first and reject lazy all-in pick-5 singles.",
    ),
    (
        "coverage_builder",
        "LLM-Coverage-Builder",
        "Use tickets, wheel, dan_tuo, or a portfolio to widen coverage under budget.",
    ),
    (
        "upside_hunter",
        "LLM-Upside-Hunter",
        "Chase asymmetric upside and justify when higher-variance prize ladders are worth it.",
    ),
)


def initial_shared_memory(budget_yuan: int) -> dict[str, str]:
    return {
        "world_goal": WORLD_GOAL,
        "current_issue": "",
        "recent_outcomes": NO_SETTLED_OUTCOME,
        "report_digest": MANUAL_REPORT_DIGEST,
        "rule_digest": NO_RULE_DIGEST,
        "purchase_budget": f"Current purchase budget: {budget_yuan} yuan.",
    }


def agent_blocks(display_name: str, description: str, bankroll_view: str = "") -> dict[str, str]:
    return {
        "persona": f"{display_name}: {description}",
        "strategy_style": description,
        "bankroll_view": bankroll_view or "Balance hit rate, payout, and budget discipline.",
        "world_goal": WORLD_GOAL,
        "current_issue": "",
        "recent_outcomes": NO_SETTLED_OUTCOME,
        "purchase_budget": "",
    }


def prediction_prompt(
    context: PredictionContext,
    prediction: StrategyPrediction,
    performance: dict[str, dict[str, object]],
) -> str:
    rank = int(performance.get(prediction.strategy_id, {}).get("rank", 999) or 999)
    return "\n".join(
        [
            f"Target period: {context.target_draw.period}",
            f"Your current numbers: {list(prediction.numbers)}",
            f"Your rationale: {prediction.rationale}",
            f"Historical rank: {rank}",
            f"Recent settled outcomes:\n{recent_outcomes_text(list(dict(context.world_state).get('settlement_history', [])))}",
            "State whether you still defend these numbers and what changed your confidence.",
        ]
    )


def issue_block(
    context: PredictionContext,
    predictions: dict[str, StrategyPrediction],
    performance: dict[str, dict[str, object]],
) -> str:
    candidates = [
        f"- {item.display_name} ({item.strategy_id}, {item.group}/{item.kind}): {list(item.numbers)}"
        for item in sorted(predictions.values(), key=lambda row: (row.group, row.strategy_id))
    ][:8]
    leaderboard = [
        f"- #{value['rank']} {value['display_name']} ({strategy_id}): objective={float(value.get('objective_score', 0.0)):.4f}, roi={float(value.get('strategy_roi', 0.0)):.2f}"
        for strategy_id, value in sorted(performance.items(), key=lambda item: int(item[1]["rank"]))
    ][:6]
    sections = [
        f"Target period: {context.target_draw.period}",
        f"History draws available: {len(context.history_draws)}",
        f"High-frequency focus numbers: {_focus_numbers(predictions) or '-'}",
        "Current candidate board:",
        *(candidates or ["- no strategy candidates"]),
        "Current leaderboard:",
        *(leaderboard or ["- no settled world rounds yet"]),
        f"Rule digest:\n{rule_digest(predictions, performance)}",
        f"Recent outcomes:\n{recent_outcomes_text(list(dict(context.world_state).get('settlement_history', [])))}",
        f"File usage policy:\n{MANUAL_REPORT_DIGEST}",
    ]
    return _limit("\n".join(sections), ISSUE_BRIEF_LIMIT)


def merge_issue_discussion(issue_base: str, digests: list[str]) -> str:
    base = str(issue_base).strip()
    latest = "\n\n".join(part.strip() for part in digests[-2:] if str(part).strip())
    if not latest:
        return _limit(base, ISSUE_BRIEF_LIMIT)
    merged = "\n\n".join([base, "Recent public discussion:", _limit(latest, DIGEST_LIMIT)])
    return _limit(merged, ISSUE_BRIEF_LIMIT)


def report_digest(context: PredictionContext, all_documents: tuple | None = None) -> str:
    docs = all_documents if all_documents is not None else context.knowledge_documents
    reports = [d for d in docs if d.kind == "report"]
    if not reports:
        return "No report documents available."
    excerpts = []
    for doc in reports[:2]:
        text = " ".join(doc.content.split())[:DIGEST_LIMIT // 2]
        excerpts.append(f"- {doc.name}: {text}")
    return _limit("\n".join(excerpts), DIGEST_LIMIT)


def prompt_passages(context: PredictionContext) -> list[str]:
    prompt_docs = list(getattr(context, "prompt_documents", ()) or ())
    if not prompt_docs:
        prompt_docs = [item for item in context.knowledge_documents if item.kind == "prompt"]
    return _document_passages(prompt_docs, PROMPT_PASSAGE_COUNT, PROMPT_PASSAGE_LIMIT)


def report_passages(context: PredictionContext) -> list[str]:
    del context
    return []


def rule_digest(
    predictions: dict[str, StrategyPrediction],
    performance: dict[str, dict[str, object]],
) -> str:
    rows = []
    for strategy_id, prediction in sorted(predictions.items()):
        if prediction.kind == "llm":
            continue
        item = performance.get(strategy_id, {})
        rows.append(
            f"- {prediction.display_name} ({strategy_id}): {list(prediction.numbers)}, objective={float(item.get('objective_score', 0.0)):.4f}, roi={float(item.get('strategy_roi', 0.0)):.2f}"
        )
    return _limit("\n".join(rows) or NO_RULE_DIGEST, DIGEST_LIMIT)


def recent_outcomes_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return NO_SETTLED_OUTCOME
    return _limit(
        "\n".join(
            f"- {item.get('period', '-')}: consensus={item.get('consensus_numbers', [])}, actual={item.get('actual_numbers', [])}, hits={item.get('consensus_hits', '-')}, best={item.get('best_hits', '-')}"
            for item in rows[-3:]
        ),
        DIGEST_LIMIT,
    )


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        payload = _json_object_prefix(cleaned)
        if payload is None:
            raise ValueError(f"Expected JSON object from Letta agent, got: {cleaned}")
        return json.loads(payload)


def debate_schema(pick_size: int) -> str:
    return f'Return JSON only: {{"numbers":[{pick_size} integers from 1-80], "comment":"...", "support_agent_ids":["..."], "rationale":"..."}}'


def comment_schema() -> str:
    return 'Return JSON only: {"comment":"...", "focus":["..."], "trusted_strategy_ids":["..."]}'


def purchase_schema() -> str:
    sizes = ",".join(str(item) for item in ALLOWED_PLAY_SIZES)
    return (
        'Return JSON only: {"plan_style":"...", "plan_type":"tickets|wheel|dan_tuo|portfolio", '
        '"play_size":5, "play_size_review":{...}, '
        '"chosen_edge":"...", "trusted_strategy_ids":["..."], "tickets":[[...]], '
        '"wheel_numbers":[...], "banker_numbers":[...], "drag_numbers":[...], '
        '"portfolio_legs":[{"plan_type":"tickets|wheel|dan_tuo","play_size":5,"tickets":[[...]],'
        '"wheel_numbers":[...],"banker_numbers":[...],"drag_numbers":[...],"primary_ticket":[...],"comment":"...","rationale":"..."}], '
        '"primary_ticket":[...], "core_numbers":[...], "hedge_numbers":[...], '
        '"candidate_numbers":[...], "avoid_numbers":[...], "support_role_ids":["..."], '
        '"comment":"...", "rationale":"..."} '
        f"(play_size must be one of {sizes})"
    )


def purchase_rule_block() -> str:
    sizes = ", ".join(str(s) for s in ALLOWED_PLAY_SIZES)
    return "\n".join(
        [
            "Happy 8 purchase rules:",
            f"Allowed play sizes: {sizes}.",
            "Each ticket costs 2 yuan. Multiplier: 1-15x.",
            *play_rule_lines(),
            "Allowed structures: tickets, wheel, dan_tuo, portfolio.",
            "Portfolio may mix multiple structures and play sizes as long as total cost stays within budget.",
            "Compare all available play sizes before choosing.",
        ]
    )


def ensure_alternate_numbers(primary: list[int], alternate: list[int]) -> list[int]:
    rows = [number for number in alternate if number not in primary]
    return rows[:ALTERNATE_NUMBER_COUNT]


def _focus_numbers(predictions: dict[str, StrategyPrediction]) -> str:
    counter: Counter[int] = Counter()
    for prediction in predictions.values():
        counter.update(int(value) for value in prediction.numbers)
    pairs = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:10]
    return ", ".join(f"{number}x{count}" for number, count in pairs)


def _json_object_prefix(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _document_passages(documents: list[object], max_chunks: int, max_chars: int) -> list[str]:
    passages = []
    for document in documents:
        source = getattr(document, "name", "unknown")
        content = _limit(str(getattr(document, "content", "")).strip(), max_chars)
        if not content:
            continue
        passages.append(f"Source: {source}\n{content}")
        if len(passages) >= max_chunks:
            break
    return passages


def _limit(text: str, limit: int) -> str:
    compact = str(text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + " ..."
