"""Chunk maintenance documents for vector search."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import blake2b
from typing import Iterable

from src.rag.document_loader import MaintenanceDocument

SECTION_MARKERS = [
    "Triệu chứng:",
    "Nguyên nhân có thể:",
    "Các bước kiểm tra:",
    "Hành động khuyến nghị:",
    "Khi nào cần escalated:",
    "Khi nào cần escalation:",
    "Khi nào cần chuyển cấp:",
]


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable chunk with source metadata."""

    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    asset_type: str
    source: str
    text: str

    def to_payload(self) -> dict[str, str]:
        """Return a Qdrant payload for this chunk."""

        return asdict(self)


def chunk_documents(
    documents: Iterable[MaintenanceDocument],
    max_chars: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """Chunk all documents while preserving metadata."""

    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, max_chars=max_chars, overlap=overlap))
    return chunks


def chunk_document(
    document: MaintenanceDocument,
    max_chars: int = 800,
    overlap: int = 120,
) -> list[DocumentChunk]:
    """Chunk one document using Vietnamese section markers with fallback splitting."""

    sections = _split_by_section_markers(document.clean_text)
    text_chunks: list[str] = []
    for section in sections:
        text_chunks.extend(_split_long_text(section, max_chars=max_chars, overlap=overlap))

    chunks: list[DocumentChunk] = []
    for index, text in enumerate(text_chunks, start=1):
        chunk_id = _stable_chunk_id(document.doc_id, index, text)
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                title=document.title,
                doc_type=document.doc_type,
                asset_type=document.asset_type,
                source=document.source,
                text=text,
            )
        )
    return chunks


def _split_by_section_markers(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    marker_pattern = "|".join(re.escape(marker) for marker in SECTION_MARKERS)
    matches = list(re.finditer(marker_pattern, normalized, flags=re.IGNORECASE))
    if not matches:
        return [normalized]

    sections: list[str] = []
    if matches[0].start() > 0:
        sections.append(normalized[: matches[0].start()].strip())

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        section = normalized[start:end].strip()
        if section:
            sections.append(section)
    return [section for section in sections if section]


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    safe_overlap = min(overlap, max_chars // 3)
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = _find_boundary(text, start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip(" ,.;")
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - safe_overlap, start + 1)
    return chunks


def _find_boundary(text: str, start: int, end: int) -> int:
    minimum = start + ((end - start) // 2)
    for separator in [". ", "; ", ", ", " "]:
        boundary = text.rfind(separator, minimum, end)
        if boundary != -1:
            return boundary + len(separator)
    return end


def _stable_chunk_id(doc_id: str, index: int, text: str) -> str:
    digest = blake2b(text.encode("utf-8"), digest_size=4).hexdigest()
    return f"{doc_id}-chunk-{index:03d}-{digest}"
