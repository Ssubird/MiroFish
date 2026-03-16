"""Asset manifest helpers for the persistent lottery world."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from .paths import DRAW_DATA_FILE, PROMPTS_DIR, REPORTS_DIR, lottery_relative_path


PROMPT_FILE = PROMPTS_DIR / "prompt.md"
MANUAL_REPORT_FILE = REPORTS_DIR / "prediction_report.md"


@dataclass(frozen=True)
class WorldAssetManifestEntry:
    name: str
    role: str
    path: str
    mtime: str
    sha256: str
    active: bool
    note: str = ""
    target_period: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "path": self.path,
            "mtime": self.mtime,
            "sha256": self.sha256,
            "active": self.active,
            "note": self.note,
            "target_period": self.target_period,
        }


def build_world_asset_manifest(target_period: str) -> tuple[dict[str, object], ...]:
    entries = [
        _manifest_entry(
            DRAW_DATA_FILE,
            "authoritative_data",
            True,
            "唯一权威数据源，包含开奖数据与命盘能量。",
            target_period,
        ),
        _manifest_entry(
            PROMPT_FILE,
            "active_prompt",
            True,
            "当前紫微斗数选号主提示词，会进入 agent 主上下文。",
        ),
        _manifest_entry(
            MANUAL_REPORT_FILE,
            "manual_reference_only",
            False,
            "仅供人工查看，不会进入 runtime、agent、grounding 或购买委员会。",
        ),
    ]
    return tuple(item.to_dict() for item in entries if item is not None)


def _manifest_entry(
    path: Path,
    role: str,
    active: bool,
    note: str,
    target_period: str | None = None,
) -> WorldAssetManifestEntry | None:
    if not path.exists():
        return None
    payload = path.read_bytes()
    return WorldAssetManifestEntry(
        name=path.name,
        role=role,
        path=_display_path(path),
        mtime=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        sha256=sha256(payload).hexdigest(),
        active=active,
        note=note,
        target_period=target_period,
    )


def _display_path(path: Path) -> str:
    try:
        return lottery_relative_path(path)
    except ValueError:
        return str(path)
