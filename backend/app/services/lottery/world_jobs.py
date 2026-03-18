"""Background execution for lottery world sessions."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from ...utils.logger import get_logger


logger = get_logger("mirofish.lottery.world_jobs")


class WorldRunManager:
    """Launch and track background world runs inside the current process."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lottery-world-run")
        self._futures: dict[str, Future] = {}
        self._lock = Lock()

    def start(self, service, strategy_ids: list[str] | None, params: dict[str, Any]) -> dict[str, object]:
        initial = service.prepare_world_session(strategy_ids=strategy_ids, **params)
        session_id = str(initial["world_session"]["session_id"])
        with self._lock:
            future = self._futures.get(session_id)
            if future is None or future.done():
                initial["world_session"] = service.queue_world_session(session_id)
                self._futures[session_id] = self._executor.submit(
                    self._run,
                    service,
                    strategy_ids,
                    {**params, "session_id": session_id},
                )
            else:
                initial["world_session"] = service.get_world_session(session_id)["session"]
        return initial

    def _run(self, service, strategy_ids: list[str] | None, params: dict[str, Any]) -> None:
        session_id = str(params["session_id"])
        try:
            service.advance_world_session(strategy_ids=strategy_ids, **params)
        except Exception as exc:
            service.record_world_session_failure(session_id, exc, runtime_mode=params.get("runtime_mode"))
            rt = service._runtime_for_session(session_id)
            if rt.store.result_exists(session_id):
                service.finalize_world_result(session_id)
            logger.exception("World session failed: %s", session_id)
        else:
            service.finalize_world_result(session_id)
        finally:
            self._cleanup(session_id)

    def _cleanup(self, session_id: str) -> None:
        with self._lock:
            self._futures.pop(session_id, None)
