"""Filesystem paths for the lottery research workspace."""

from pathlib import Path

from ...config import Config


LOTTERY_ROOT = Path(Config.LOTTERY_DATA_ROOT).resolve()
DATA_DIR = LOTTERY_ROOT / "data"
DRAWS_DIR = DATA_DIR / "draws"
CHARTS_DIR = DATA_DIR / "charts"
KNOWLEDGE_DIR = LOTTERY_ROOT / "knowledge" / "learn"
PROMPTS_DIR = LOTTERY_ROOT / "knowledge" / "prompts"
REPORTS_DIR = LOTTERY_ROOT / "reports"
DRAW_DATA_FILE = DRAWS_DIR / "keno8_predict_data.json"


def lottery_relative_path(path: Path) -> str:
    """Return a stable relative path for API responses."""
    return path.resolve().relative_to(LOTTERY_ROOT).as_posix()
