"""Persisted Zep graph metadata for the lottery workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ZepGraphState:
    """Persisted remote graph metadata."""

    graph_id: str
    synced_at: str
    workspace_digest: str
    document_count: int
    chart_count: int
    draw_count: int
    node_count: int
    edge_count: int


class ZepGraphStateStore:
    """Small JSON store for the active remote graph."""

    def __init__(self, state_file: Path):
        self.state_file = state_file

    def load(self) -> ZepGraphState | None:
        if not self.state_file.exists():
            return None
        payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        return ZepGraphState(**payload)

    def save(self, state: ZepGraphState) -> None:
        self.state_file.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
