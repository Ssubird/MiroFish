"""Filesystem persistence for lottery world sessions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any

from ...config import Config
from .world_models import WorldEvent, WorldSession, world_now


CURRENT_FILE = "current_session.txt"
SESSION_FILE = "session.json"
RESULT_FILE = "result.json"
TIMELINE_FILE = "timeline.jsonl"
CACHE_DIR = "result_cache"
READ_RETRY_COUNT = 5
READ_RETRY_DELAY_SECONDS = 0.02
WRITE_RETRY_COUNT = 8
WRITE_RETRY_DELAY_SECONDS = 0.05


class WorldSessionStore:
    """Persist world sessions, results, and timeline events to local files."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or Config.LOTTERY_WORLD_STATE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: WorldSession) -> None:
        self._session_path(session.session_id).mkdir(parents=True, exist_ok=True)
        payload = session.to_dict()
        payload["updated_at"] = world_now()
        self._write_json(self._session_file(session.session_id), payload)
        self._current_file().write_text(session.session_id, encoding="utf-8")

    def load_session(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self._session_file(session_id))

    def load_current_session(self) -> dict[str, Any]:
        session_id = self.current_session_id()
        if not session_id:
            raise FileNotFoundError("No current world session")
        return self.load_session(session_id)

    def current_session_id(self) -> str | None:
        path = self._current_file()
        if not path.exists():
            return None
        session_id = path.read_text(encoding="utf-8").strip()
        return session_id or None

    def reset_current_session(self) -> None:
        self._current_file().write_text("", encoding="utf-8")

    def save_result(self, session_id: str, payload: dict[str, Any]) -> None:
        self._session_path(session_id).mkdir(parents=True, exist_ok=True)
        self._write_json(self._result_file(session_id), payload)

    def load_result(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self._result_file(session_id))

    def result_exists(self, session_id: str) -> bool:
        return self._result_file(session_id).exists()

    def append_events(self, session_id: str, events: list[WorldEvent]) -> None:
        if not events:
            return
        self._session_path(session_id).mkdir(parents=True, exist_ok=True)
        with self._timeline_file(session_id).open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def list_events(
        self,
        session_id: str,
        offset: int = 0,
        limit: int = 50,
        latest: bool = False,
    ) -> dict[str, Any]:
        path = self._timeline_file(session_id)
        if not path.exists():
            return {"total": 0, "items": [], "offset": 0, "limit": limit}
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        window = max(limit, 0)
        if latest:
            end = len(rows)
            start = max(end - window, 0)
        else:
            start = max(offset, 0)
            end = start + window
        return {"total": len(rows), "items": rows[start:end], "offset": start, "limit": window}

    def session_exists(self, session_id: str) -> bool:
        return self._session_file(session_id).exists()

    def load_result_cache(self, key_parts: tuple[str, ...]) -> dict[str, Any] | None:
        path = self._cache_file(key_parts)
        if not path.exists():
            return None
        return self._read_json(path)

    def save_result_cache(self, key_parts: tuple[str, ...], payload: dict[str, Any]) -> None:
        path = self._cache_file(key_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, payload)

    def _session_path(self, session_id: str) -> Path:
        return self.root / session_id

    def _current_file(self) -> Path:
        return self.root / CURRENT_FILE

    def _session_file(self, session_id: str) -> Path:
        return self._session_path(session_id) / SESSION_FILE

    def _result_file(self, session_id: str) -> Path:
        return self._session_path(session_id) / RESULT_FILE

    def _timeline_file(self, session_id: str) -> Path:
        return self._session_path(session_id) / TIMELINE_FILE

    def _cache_file(self, key_parts: tuple[str, ...]) -> Path:
        digest = hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()
        return self.root / CACHE_DIR / f"{digest}.json"

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        last_error = None
        for _ in range(READ_RETRY_COUNT):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (PermissionError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(READ_RETRY_DELAY_SECONDS)
        if last_error is not None:
            raise last_error
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = self._tmp_json_path(path)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp_path.write_text(content, encoding="utf-8")
        self._replace_with_retry(tmp_path, path)

    def _replace_with_retry(self, src: Path, dst: Path) -> None:
        last_error = None
        for _ in range(WRITE_RETRY_COUNT):
            try:
                src.replace(dst)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(WRITE_RETRY_DELAY_SECONDS)
        self._cleanup_tmp(src)
        if last_error is not None:
            raise last_error
        src.replace(dst)

    def _tmp_json_path(self, path: Path) -> Path:
        suffix = f"{path.suffix}.{time.time_ns()}.tmp"
        return path.with_suffix(suffix)

    def _cleanup_tmp(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            return
