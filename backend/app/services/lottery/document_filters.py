"""Document filtering helpers for lottery grounding."""

from __future__ import annotations


GROUNDING_KINDS = frozenset({"knowledge"})
PROMPT_KINDS = frozenset({"prompt"})
MANUAL_REFERENCE_KINDS = frozenset({"report"})


def grounding_documents(documents, target_draw=None):
    del target_draw
    return tuple(item for item in documents if getattr(item, "kind", "") in GROUNDING_KINDS)


def prompt_documents(documents):
    return tuple(item for item in documents if getattr(item, "kind", "") in PROMPT_KINDS)


def manual_reference_documents(documents):
    return tuple(item for item in documents if getattr(item, "kind", "") in MANUAL_REFERENCE_KINDS)
