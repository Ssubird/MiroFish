"""Prompt-asset helpers for world_v2 market roles."""

from __future__ import annotations

from typing import Mapping


HANDBOOK_PROMPT_DOC = "lottery_handbook_deep_notes.md"
PROMPT_ASSET_PASSAGE_CHAR_LIMIT = 2800
PROMPT_ASSET_DIRECT_CHUNK_CHAR_LIMIT = 2800


def agent_prompt_passages(ref, context) -> list[str]:
    document_names = _document_names(getattr(ref, "metadata", {}))
    if not document_names:
        return []
    passages = []
    for item in _matching_prompt_docs(context, document_names):
        passages.extend(_document_chunks(item.name, item.content, "Source", PROMPT_ASSET_PASSAGE_CHAR_LIMIT))
    return passages


def direct_prompt_block(agent_row: Mapping[str, object], documents) -> str:
    metadata = dict(agent_row.get("metadata") or {})
    document_names = _document_names(metadata)
    if not document_names:
        return ""
    docs = _matching_docs(documents or (), document_names)
    if not docs:
        return ""
    lines = []
    note = str(metadata.get("direct_prompt_note", "")).strip()
    if note:
        lines.append(f"Role doctrine:\n{note}")
    for item in docs:
        lines.extend(_document_chunks(item.name, item.content, "Prompt asset", PROMPT_ASSET_DIRECT_CHUNK_CHAR_LIMIT))
    return "\n\n".join(lines)


def handbook_role_metadata(note: str = "") -> dict[str, object]:
    metadata = {"prompt_document_names": (HANDBOOK_PROMPT_DOC,)}
    if note:
        metadata["direct_prompt_note"] = note
    return metadata


def _matching_prompt_docs(context, document_names: tuple[str, ...]) -> list[object]:
    prompt_docs = list(getattr(context, "prompt_documents", ()) or ())
    if not prompt_docs:
        prompt_docs = [item for item in context.knowledge_documents if getattr(item, "kind", "") == "prompt"]
    return _matching_docs(prompt_docs, document_names)


def _matching_docs(documents, document_names: tuple[str, ...]) -> list[object]:
    wanted = {item.lower() for item in document_names}
    return [item for item in documents if str(getattr(item, "name", "")).lower() in wanted]


def _document_names(metadata: Mapping[str, object]) -> tuple[str, ...]:
    raw = metadata.get("prompt_document_names")
    if not isinstance(raw, (list, tuple)):
        return ()
    rows = []
    for item in raw:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    return tuple(rows)


def _document_chunks(name: str, content: str, label: str, limit: int) -> list[str]:
    text = str(content or "").strip()
    if not text:
        return []
    chunks = _split_chunks(text, limit)
    total = len(chunks)
    return [
        f"{label} [{name}] part {index}/{total}:\n{chunk}"
        for index, chunk in enumerate(chunks, start=1)
    ]


def _split_chunks(text: str, limit: int) -> list[str]:
    parts = [item.strip() for item in text.split("\n\n") if item.strip()]
    if not parts:
        return [text[:limit]]
    chunks: list[str] = []
    current = ""
    for part in parts:
        current = _append_part(chunks, current, part, limit)
    if current:
        chunks.append(current)
    return chunks


def _append_part(chunks: list[str], current: str, part: str, limit: int) -> str:
    candidate = f"{current}\n\n{part}".strip() if current else part
    if len(candidate) <= limit:
        return candidate
    if current:
        chunks.append(current)
        return _append_part(chunks, "", part, limit)
    for index in range(0, len(part), limit):
        chunk = part[index : index + limit].strip()
        if chunk:
            chunks.append(chunk)
    return ""
