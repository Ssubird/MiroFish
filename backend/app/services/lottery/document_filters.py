"""Document filtering helpers for lottery grounding."""

from __future__ import annotations

from .report_scope import report_is_visible


GROUNDING_KINDS = frozenset({"knowledge", "prompt", "report"})


def grounding_documents(documents, target_draw=None):
    return tuple(item for item in documents if _is_grounding_document(item, target_draw))


def _is_grounding_document(document, target_draw) -> bool:
    kind = getattr(document, "kind", "")
    if kind in {"knowledge", "prompt"}:
        return True
    if kind != "report":
        return False
    return report_is_visible(document, target_draw)
