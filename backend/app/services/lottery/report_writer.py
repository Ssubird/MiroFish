"""Write structured lottery reports to disk."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .issue_report import build_issue_report_payload, issue_report_stem, pending_issue_report_item
from .issue_report_markdown import build_issue_report_markdown
from .paths import REPORTS_DIR, lottery_relative_path
from .report_markdown import build_markdown_report


REPORT_PREFIX = "lottery-backtest"
LEDGER_BASENAME = "lottery-issue-ledger"
ISSUE_DIRNAME = "issues"


class LotteryReportWriter:
    """Persist world payloads, per-issue reports, and the cumulative ledger."""

    def __init__(self, report_dir: Path | None = None):
        self.report_dir = report_dir or REPORTS_DIR

    def write(self, payload: dict[str, object]) -> dict[str, object]:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        saved_at = datetime.now().isoformat(timespec="seconds")
        paths = self._report_paths(run_id)
        artifacts = self._artifact_summary(run_id, saved_at, paths)
        enriched = dict(payload)
        ledger_artifacts = self._write_issue_reports(enriched)
        enriched["report_artifacts"] = artifacts | ledger_artifacts
        paths["json"].write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["markdown"].write_text(build_markdown_report(enriched), encoding="utf-8")
        return dict(enriched["report_artifacts"])

    def _write_issue_reports(self, payload: dict[str, object]) -> dict[str, object]:
        session = dict(payload.get("world_session") or {})
        evaluation = dict(payload.get("evaluation") or {})
        ledger = list(session.get("issue_ledger") or [])
        latest_review = dict(session.get("latest_review") or {})
        pending_item = pending_issue_report_item(payload, session)
        if not ledger and pending_item is None:
            return {"issue_reports": [], "issue_ledger": None, "latest_review": latest_review}

        issues_dir = self.report_dir / ISSUE_DIRNAME
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_reports = []
        issue_items = list(ledger)
        written_periods = {
            str(item.get("predicted_period", "")).strip()
            for item in issue_items
            if isinstance(item, dict)
        }
        pending_period = str((pending_item or {}).get("predicted_period", "")).strip()
        if pending_period and pending_period not in written_periods:
            issue_items.append(dict(pending_item or {}))

        for item in issue_items:
            period = str(item.get("predicted_period", "")).strip()
            if not period:
                continue
            report_payload = build_issue_report_payload(item, session, evaluation)
            stem = issue_report_stem(period)
            issue_paths = {
                "json": issues_dir / f"{stem}.json",
                "markdown": issues_dir / f"{stem}.md",
            }
            issue_paths["json"].write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            issue_paths["markdown"].write_text(build_issue_report_markdown(report_payload), encoding="utf-8")
            issue_reports.append(
                {
                    "predicted_period": period,
                    "report_name": stem,
                    "json_path": self._display_path(issue_paths["json"]),
                    "markdown_path": self._display_path(issue_paths["markdown"]),
                }
            )

        ledger_paths = {
            "json": self.report_dir / f"{LEDGER_BASENAME}.json",
            "markdown": self.report_dir / f"{LEDGER_BASENAME}.md",
        }
        ledger_paths["json"].write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        ledger_paths["markdown"].write_text(_ledger_markdown(ledger), encoding="utf-8")
        return {
            "issue_reports": issue_reports,
            "issue_ledger": {
                "json_path": self._display_path(ledger_paths["json"]),
                "markdown_path": self._display_path(ledger_paths["markdown"]),
            },
            "latest_review": latest_review,
        }

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


def _ledger_markdown(ledger: list[dict[str, object]]) -> str:
    lines = [
        "# Lottery Issue Ledger",
        "",
        "| Period | Visible Through | Official Hits | Purchase Profit | Purchase ROI |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in ledger:
        purchase = dict(item.get("purchase_recommendation") or {})
        lines.append(
            f"| {item.get('predicted_period', '-')} | {item.get('visible_through_period', '-')} | "
            f"{item.get('official_hits', '-')} | {purchase.get('profit_yuan', '-')} | {purchase.get('roi', '-')} |"
        )
    lines.append("")
    for item in ledger:
        lines.extend(_issue_summary_lines(item))
    return "\n".join(lines).strip() + "\n"


def _issue_summary_lines(item: dict[str, object]) -> list[str]:
    purchase = dict(item.get("purchase_recommendation") or {})
    review = dict(item.get("latest_review") or {})
    return [
        f"## Issue {item.get('predicted_period', '-')}",
        "",
        f"- Visible Through: `{item.get('visible_through_period', '-')}`",
        f"- Official Prediction: `{_number_line(item.get('official_prediction', []))}`",
        f"- Official Alternates: `{_number_line(item.get('official_alternate_numbers', []))}`",
        f"- Actual Numbers: `{_number_line(item.get('actual_numbers', []))}`",
        f"- Official Hits: `{item.get('official_hits', '-')}`",
        f"- Purchase Plan Type: `{purchase.get('plan_type', '-')}`",
        f"- Purchase Play Size: `{purchase.get('play_size', '-')}`",
        f"- Purchase Numbers: `{_number_line(purchase.get('numbers', []))}`",
        f"- Purchase Cost: `{purchase.get('cost_yuan', '-')}`",
        f"- Purchase Payout: `{purchase.get('payout_yuan', '-')}`",
        f"- Purchase Profit: `{purchase.get('profit_yuan', '-')}`",
        f"- Purchase ROI: `{purchase.get('roi', '-')}`",
        f"- Review Summary: {review.get('summary', '-')}",
        "",
    ]


def _number_line(values) -> str:
    rows = [str(value) for value in values or []]
    return ", ".join(rows) or "-"
