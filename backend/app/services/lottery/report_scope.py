"""Time-sliced visibility rules for report grounding."""

from __future__ import annotations

from datetime import date, datetime


def report_is_visible(document, target_draw) -> bool:
    metadata = dict(getattr(document, "metadata", {}) or {})
    if getattr(document, "kind", "") != "report" or target_draw is None:
        return False
    if not _scope_complete(metadata):
        return False
    if not _period_in_window(
        str(target_draw.period),
        str(metadata.get("effective_period", "")).strip(),
        str(metadata.get("max_visible_period", "")).strip(),
    ):
        return False
    return _created_before_target(metadata.get("created_at"), str(target_draw.date))


def report_scope(document) -> dict[str, object]:
    metadata = dict(getattr(document, "metadata", {}) or {})
    return {
        "created_at": metadata.get("created_at"),
        "effective_period": metadata.get("effective_period"),
        "max_visible_period": metadata.get("max_visible_period"),
        "scope_source": metadata.get("scope_source"),
        "scope_complete": _scope_complete(metadata),
    }


def _period_in_window(current_period: str, effective_period: str, max_visible_period: str) -> bool:
    if not effective_period or not max_visible_period:
        return False
    current = _parse_period(current_period)
    return _parse_period(effective_period) < current <= _parse_period(max_visible_period)


def _parse_period(value: str) -> int:
    digits = "".join(char for char in value if char.isdigit())
    return int(digits) if digits else -1


def _created_before_target(created_at: object, target_date: str) -> bool:
    created_date = _parse_created_date(created_at)
    target = _parse_target_date(target_date)
    if created_date is None or target is None:
        return False
    return created_date <= target


def _parse_created_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return _parse_target_date(text)


def _parse_target_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _scope_complete(metadata: dict[str, object]) -> bool:
    return bool(
        str(metadata.get("created_at", "")).strip()
        and str(metadata.get("effective_period", "")).strip()
        and str(metadata.get("max_visible_period", "")).strip()
    )
