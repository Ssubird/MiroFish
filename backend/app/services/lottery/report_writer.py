"""Write structured lottery backtest reports to disk."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .paths import REPORTS_DIR, lottery_relative_path
from .report_markdown import build_markdown_report


REPORT_PREFIX = "lottery-backtest"


class LotteryReportWriter:
    """Persist each run as JSON and Markdown for later analysis."""

    def __init__(self, report_dir: Path | None = None):
        self.report_dir = report_dir or REPORTS_DIR

    def write(self, payload: dict[str, object]) -> dict[str, object]:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        saved_at = datetime.now().isoformat(timespec="seconds")
        paths = self._report_paths(run_id)
        artifacts = self._artifact_summary(run_id, saved_at, paths)
        enriched = dict(payload)
        enriched["report_artifacts"] = artifacts
        paths["json"].write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["markdown"].write_text(build_markdown_report(enriched), encoding="utf-8")
        return artifacts

    def _report_paths(self, run_id: str) -> dict[str, Path]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        return {
            "json": self.report_dir / f"{REPORT_PREFIX}-{run_id}.json",
            "markdown": self.report_dir / f"{REPORT_PREFIX}-{run_id}.md",
        }

    def _artifact_summary(self, run_id: str, saved_at: str, paths: dict[str, Path]) -> dict[str, object]:
        return {
            "run_id": run_id,
            "saved_at": saved_at,
            "json_path": self._display_path(paths["json"]),
            "markdown_path": self._display_path(paths["markdown"]),
        }

    def _display_path(self, path: Path) -> str:
        try:
            return lottery_relative_path(path)
        except ValueError:
            return str(path)
