"""Data access for the lottery research workspace."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re

from .models import ChartProfile, DrawRecord, EnergySignature, KnowledgeDocument
from .paths import CHARTS_DIR, DRAW_DATA_FILE, KNOWLEDGE_DIR, PROMPTS_DIR, REPORTS_DIR, lottery_relative_path
from .vocabulary import extract_domain_terms


MARKDOWN_SUFFIXES = (".md", ".markdown", ".txt")
CHART_SUFFIXES = (".json", ".md", ".markdown", ".txt")
REPORT_PERIOD_PATTERN = re.compile(r"\b20\d{5}\b")
REPORT_TIMESTAMP_PATTERN = re.compile(r"20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")


class LotteryDataRepository:
    """Load structured draw data and research assets."""

    def load_draws(self) -> list[DrawRecord]:
        if not DRAW_DATA_FILE.exists():
            raise FileNotFoundError(f"未找到开奖数据文件: {DRAW_DATA_FILE}")
        raw_data = json.loads(DRAW_DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw_data, list) or not raw_data:
            raise ValueError("开奖数据文件为空或格式不正确")
        return [self._parse_draw(item, index) for index, item in enumerate(raw_data, start=1)]

    def load_knowledge_documents(self) -> list[KnowledgeDocument]:
        documents = []
        documents.extend(self._scan_markdown_dir(KNOWLEDGE_DIR, "knowledge"))
        documents.extend(self._scan_markdown_dir(PROMPTS_DIR, "prompt"))
        documents.extend(self._scan_markdown_dir(REPORTS_DIR, "report"))
        return sorted(documents, key=lambda item: (item.kind, item.name))

    def load_chart_profiles(self) -> list[ChartProfile]:
        profiles = []
        profiles.extend(self._scan_chart_dir())
        profiles.extend(self._load_draw_embedded_charts())
        return profiles

    def _parse_draw(self, item: object, index: int) -> DrawRecord:
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条开奖记录不是对象")
        numbers = tuple(int(number) for number in item.get("numbers", []))
        return DrawRecord(
            period=str(item.get("period", "")),
            date=str(item.get("date", "")),
            chinese_date=str(item.get("chineseDate", "")),
            numbers=numbers,
            daily_energy=EnergySignature.from_dict(item.get("daily_energy")),
            hourly_energy=EnergySignature.from_dict(item.get("hourly_energy")),
        )

    def _scan_markdown_dir(self, base_dir: Path, kind: str) -> list[KnowledgeDocument]:
        if not base_dir.exists():
            raise FileNotFoundError(f"未找到目录: {base_dir}")
        documents = []
        for path in sorted(base_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in MARKDOWN_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8")
            documents.append(
                KnowledgeDocument(
                    name=path.name,
                    kind=kind,
                    relative_path=lottery_relative_path(path),
                    char_count=len(content),
                    content=content,
                    terms=extract_domain_terms(content),
                    metadata=self._document_metadata(path, kind, content),
                )
            )
        return documents

    def _document_metadata(self, path: Path, kind: str, content: str) -> dict[str, object]:
        if kind != "report":
            return {}
        return self._report_metadata(path, content)

    def _report_metadata(self, path: Path, content: str) -> dict[str, object]:
        json_path = path.with_suffix(".json")
        if json_path.exists():
            return self._report_metadata_from_json(json_path)
        return self._report_metadata_from_markdown(content)

    def _report_metadata_from_json(self, json_path: Path) -> dict[str, object]:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return self._report_metadata_from_ledger(payload, json_path)
        dataset = payload.get("dataset") or {}
        artifacts = payload.get("report_artifacts") or {}
        return {
            "created_at": str(artifacts.get("saved_at", "")).strip(),
            "effective_period": str(dataset.get("latest_completed_period", "")).strip(),
            "max_visible_period": str(dataset.get("pending_target_period", "")).strip(),
            "scope_source": "json_artifact",
        }

    def _report_metadata_from_ledger(
        self,
        payload: list[object],
        json_path: Path,
    ) -> dict[str, object]:
        latest = next(
            (item for item in reversed(payload) if isinstance(item, dict)),
            {},
        )
        created_at = ""
        if json_path.exists():
            created_at = datetime.fromtimestamp(json_path.stat().st_mtime, UTC).isoformat()
        return {
            "created_at": str(created_at),
            "effective_period": str(latest.get("predicted_period", "")).strip(),
            "max_visible_period": str(latest.get("visible_through_period", "")).strip(),
            "scope_source": "json_issue_ledger",
        }

    def _report_metadata_from_markdown(self, content: str) -> dict[str, object]:
        effective_period, max_visible_period = report_period_bounds(REPORT_PERIOD_PATTERN.findall(content))
        return {
            "created_at": self._report_created_at(content),
            "effective_period": effective_period,
            "max_visible_period": max_visible_period,
            "scope_source": "markdown_heuristic",
        }

    def _report_created_at(self, content: str) -> str:
        match = REPORT_TIMESTAMP_PATTERN.search(content)
        return match.group(0) if match else ""

    def _scan_chart_dir(self) -> list[ChartProfile]:
        if not CHARTS_DIR.exists():
            return []
        profiles = []
        for path in sorted(CHARTS_DIR.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in CHART_SUFFIXES:
                continue
            profiles.append(self._parse_chart_profile(path))
        return profiles

    def _load_draw_embedded_charts(self) -> list[ChartProfile]:
        raw_data = json.loads(DRAW_DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw_data, list):
            raise ValueError("开奖数据文件中的命盘信息格式不正确")
        return [self._to_draw_chart_profile(item, index) for index, item in enumerate(raw_data, start=1)]

    def _to_draw_chart_profile(self, item: object, index: int) -> ChartProfile:
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条开奖记录不是对象，无法提取命盘")
        period = str(item.get("period", ""))
        payload = {
            "period": period,
            "date": str(item.get("date", "")),
            "chineseDate": str(item.get("chineseDate", "")),
            "daily_energy": item.get("daily_energy", {}),
            "hourly_energy": item.get("hourly_energy", {}),
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return ChartProfile(
            name=f"draw-chart-{period}.json",
            kind="draw_chart",
            relative_path=f"{lottery_relative_path(DRAW_DATA_FILE)}#{period}",
            char_count=len(content),
            content=content,
            feature_terms=extract_domain_terms(content),
            metadata={"period": period, "source": "draw_file", "has_numbers": bool(item.get("numbers"))},
        )

    def _parse_chart_profile(self, path: Path) -> ChartProfile:
        if path.suffix.lower() == ".json":
            return self._parse_chart_json(path)
        content = path.read_text(encoding="utf-8")
        return ChartProfile(
            name=path.name,
            kind="chart",
            relative_path=lottery_relative_path(path),
            char_count=len(content),
            content=content,
            feature_terms=extract_domain_terms(content),
        )

    def _parse_chart_json(self, path: Path) -> ChartProfile:
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return ChartProfile(
            name=path.name,
            kind="chart",
            relative_path=lottery_relative_path(path),
            char_count=len(text),
            content=text,
            feature_terms=extract_domain_terms(text),
            metadata=payload if isinstance(payload, dict) else {"root_type": type(payload).__name__},
        )


def report_period_bounds(periods: list[str]) -> tuple[str, str]:
    ordered = ordered_periods(periods)
    if not ordered:
        return "", ""
    if len(ordered) == 1:
        return prior_period(ordered[0]), ordered[0]
    return ordered[-2], ordered[-1]


def ordered_periods(periods: list[str]) -> list[str]:
    unique = []
    for period in periods:
        if period not in unique:
            unique.append(period)
    return sorted(unique, key=parse_period_token)


def parse_period_token(value: str) -> int:
    digits = "".join(char for char in value if char.isdigit())
    return int(digits) if digits else -1


def prior_period(period: str) -> str:
    digits = "".join(char for char in period if char.isdigit())
    if not digits:
        return ""
    previous = max(int(digits) - 1, 0)
    return f"{previous:0{len(digits)}d}"
