"""Multi-agent dialogue orchestration for lottery strategies."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .agents import StrategyAgent
from .models import PredictionContext, StrategyPrediction


MIN_ACTIVE_PARTICIPANTS = 3
MAX_ACTIVE_PARTICIPANTS = 6
GROUP_PRIORITY = {"social": 0, "judge": 1, "hybrid": 2, "metaphysics": 3, "data": 4}


@dataclass(frozen=True)
class DialogueResult:
    predictions: dict[str, StrategyPrediction]
    rounds: list[dict[str, object]]


@dataclass(frozen=True)
class RoundTask:
    context: PredictionContext
    strategy: StrategyAgent
    own_prediction: StrategyPrediction
    peer_predictions: dict[str, dict[str, object]]
    dialogue_history: tuple[dict[str, object], ...]
    pick_size: int
    round_index: int


class DialogueCoordinator:
    """Run explicit discussion rounds for dialogue-capable agents."""

    def run(
        self,
        context: PredictionContext,
        strategies: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        pick_size: int,
        rounds: int,
        parallelism: int = 1,
        stage_prefix: str = "dialogue",
        title_prefix: str = "Dialogue Round",
    ) -> DialogueResult:
        participants = self._participants(strategies, predictions)
        return self._dialogue_loop(
            context,
            participants,
            predictions,
            pick_size,
            rounds,
            parallelism,
            stage_prefix,
            title_prefix,
            dynamic=False,
        )

    def run_society(
        self,
        context: PredictionContext,
        strategies: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        pick_size: int,
        rounds: int,
        parallelism: int = 1,
    ) -> DialogueResult:
        participants = self._participants(strategies, predictions)
        return self._dialogue_loop(
            context,
            participants,
            predictions,
            pick_size,
            rounds,
            parallelism,
            "society",
            "Society Round",
            dynamic=True,
        )

    def _dialogue_loop(
        self,
        context: PredictionContext,
        participants: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        pick_size: int,
        rounds: int,
        parallelism: int,
        stage_prefix: str,
        title_prefix: str,
        dynamic: bool,
    ) -> DialogueResult:
        if rounds <= 0 or not participants or len(predictions) <= 1:
            return DialogueResult(predictions=dict(predictions), rounds=[])
        current = dict(predictions)
        history: list[dict[str, object]] = []
        traces = []
        for round_index in range(1, rounds + 1):
            active = self._active_participants(context, participants, current, round_index, dynamic)
            current, round_items = self._run_round(
                context,
                active,
                current,
                tuple(history),
                pick_size,
                round_index,
                parallelism,
            )
            history.extend(round_items)
            traces.append(self._round_trace(stage_prefix, title_prefix, round_index, active, round_items, current))
        return DialogueResult(predictions=current, rounds=traces)

    def _participants(
        self,
        strategies: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
    ) -> dict[str, StrategyAgent]:
        return {
            strategy_id: strategy
            for strategy_id, strategy in strategies.items()
            if bool(getattr(strategy, "supports_dialogue", False)) and strategy_id in predictions
        }

    def _active_participants(
        self,
        context: PredictionContext,
        participants: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        round_index: int,
        dynamic: bool,
    ) -> dict[str, StrategyAgent]:
        ordered = sorted(participants, key=lambda strategy_id: self._activity_key(context, predictions, strategy_id))
        if not dynamic or len(ordered) <= MIN_ACTIVE_PARTICIPANTS:
            return {strategy_id: participants[strategy_id] for strategy_id in ordered}
        target = min(MAX_ACTIVE_PARTICIPANTS, max(MIN_ACTIVE_PARTICIPANTS, len(ordered) // 2 + 1))
        rotated = ordered[round_index - 1 :] + ordered[: round_index - 1]
        selected = self._group_balanced_selection(rotated, predictions, target)
        return {strategy_id: participants[strategy_id] for strategy_id in selected}

    def _activity_key(
        self,
        context: PredictionContext,
        predictions: dict[str, StrategyPrediction],
        strategy_id: str,
    ) -> tuple[int, int, int, str]:
        prediction = predictions[strategy_id]
        performance = dict(context.strategy_performance.get(strategy_id, {}))
        social_state = dict(context.social_state.get(strategy_id, {}))
        return (
            GROUP_PRIORITY.get(prediction.group, 99),
            int(performance.get("rank", 999) or 999),
            -len(social_state.get("revision_history", [])),
            strategy_id,
        )

    def _group_balanced_selection(
        self,
        ordered: list[str],
        predictions: dict[str, StrategyPrediction],
        target: int,
    ) -> list[str]:
        selected = []
        groups = []
        for strategy_id in ordered:
            group = predictions[strategy_id].group
            if group in groups:
                continue
            selected.append(strategy_id)
            groups.append(group)
            if len(selected) >= target:
                return selected
        for strategy_id in ordered:
            if strategy_id not in selected:
                selected.append(strategy_id)
            if len(selected) >= target:
                return selected
        return selected

    def _run_round(
        self,
        context: PredictionContext,
        participants: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
        parallelism: int,
    ) -> tuple[dict[str, StrategyPrediction], list[dict[str, object]]]:
        tasks = self._round_tasks(context, participants, predictions, history, pick_size, round_index)
        if parallelism <= 1 or len(tasks) <= 1:
            return self._sequential_round(tasks, predictions)
        return self._parallel_round(tasks, predictions, parallelism)

    def _round_tasks(
        self,
        context: PredictionContext,
        participants: dict[str, StrategyAgent],
        predictions: dict[str, StrategyPrediction],
        history: tuple[dict[str, object], ...],
        pick_size: int,
        round_index: int,
    ) -> dict[str, RoundTask]:
        return {
            strategy_id: RoundTask(
                context=context,
                strategy=strategy,
                own_prediction=predictions[strategy_id],
                peer_predictions=self._peer_snapshot(predictions, strategy_id),
                dialogue_history=history,
                pick_size=pick_size,
                round_index=round_index,
            )
            for strategy_id, strategy in participants.items()
        }

    def _sequential_round(
        self,
        tasks: dict[str, RoundTask],
        predictions: dict[str, StrategyPrediction],
    ) -> tuple[dict[str, StrategyPrediction], list[dict[str, object]]]:
        current = dict(predictions)
        notes = []
        for strategy_id, task in tasks.items():
            next_prediction, note = self._deliberate(task)
            current[strategy_id] = next_prediction
            notes.append(note)
        return current, notes

    def _parallel_round(
        self,
        tasks: dict[str, RoundTask],
        predictions: dict[str, StrategyPrediction],
        parallelism: int,
    ) -> tuple[dict[str, StrategyPrediction], list[dict[str, object]]]:
        max_workers = min(parallelism, len(tasks))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lottery-dialogue") as pool:
            futures = {strategy_id: pool.submit(self._deliberate, task) for strategy_id, task in tasks.items()}
            current = dict(predictions)
            notes = []
            for strategy_id in tasks:
                next_prediction, note = futures[strategy_id].result()
                current[strategy_id] = next_prediction
                notes.append(note)
        return current, notes

    def _deliberate(self, task: RoundTask) -> tuple[StrategyPrediction, dict[str, object]]:
        return task.strategy.deliberate(
            context=task.context,
            own_prediction=task.own_prediction,
            peer_predictions=task.peer_predictions,
            dialogue_history=task.dialogue_history,
            pick_size=task.pick_size,
            round_index=task.round_index,
        )

    def _round_trace(
        self,
        stage_prefix: str,
        title_prefix: str,
        round_index: int,
        participants: dict[str, StrategyAgent],
        round_items: list[dict[str, object]],
        predictions: dict[str, StrategyPrediction],
    ) -> dict[str, object]:
        active_ids = list(participants.keys())
        active_groups = sorted({predictions[strategy_id].group for strategy_id in active_ids})
        return {
            "stage": f"{stage_prefix}_round_{round_index}",
            "title": f"{title_prefix} {round_index}",
            "active_strategy_ids": active_ids,
            "active_groups": active_groups,
            "items": round_items,
        }

    def _peer_snapshot(
        self,
        predictions: dict[str, StrategyPrediction],
        exclude_strategy_id: str,
    ) -> dict[str, dict[str, object]]:
        return {
            strategy_id: {
                "display_name": prediction.display_name,
                "group": prediction.group,
                "kind": prediction.kind,
                "numbers": list(prediction.numbers),
                "rationale": prediction.rationale,
            }
            for strategy_id, prediction in predictions.items()
            if strategy_id != exclude_strategy_id
        }
