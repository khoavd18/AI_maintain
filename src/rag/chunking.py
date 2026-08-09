"""Chunk maintenance documents for vector search."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import blake2b
from typing import Iterable
import unicodedata

from src.rag.document_loader import MaintenanceDocument

SECTION_MARKERS = [
    "Phạm vi:",
    "An toàn:",
    "Triệu chứng:",
    "Nguyên nhân có thể:",
    "Các bước kiểm tra:",
    "Quy trình xử lý:",
    "Hành động khuyến nghị:",
    "Bảo trì định kỳ:",
    "Cảnh báo:",
    "Điều kiện vận hành:",
    "Tài liệu tham khảo:",
    "Khi nào cần hỗ trợ chuyên môn:",
    "Khi nào cần chuyển cấp:",
    "Giới hạn:",
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
    failure_category: str = ""
    version: str = "1.0"
    effective_date: str = ""
    language: str = "vi"
    chunk_index: int = 0

    def to_payload(self) -> dict[str, str | int]:
        """Return a Qdrant payload for this chunk."""

        payload: dict[str, str | int] = asdict(self)
        payload.update(
            {
                "document_id": self.doc_id,
                "document_type": self.doc_type,
                "content": self.text,
            }
        )
        return payload


def chunk_documents(
    documents: Iterable[MaintenanceDocument],
    max_chars: int = 800,
    overlap: int = 80,
) -> list[DocumentChunk]:
    """Chunk all documents while preserving metadata."""

    chunks: list[DocumentChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, max_chars=max_chars, overlap=overlap))
    return chunks


def chunk_document(
    document: MaintenanceDocument,
    max_chars: int = 800,
    overlap: int = 80,
) -> list[DocumentChunk]:
    """Chunk one document using Vietnamese section markers with fallback splitting."""

    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars.")
    sections = _split_by_section_markers(document.content)
    text_chunks: list[str] = []
    for section in sections:
        text_chunks.extend(_split_section(section, max_chars=max_chars, overlap=overlap))

    chunks: list[DocumentChunk] = []
    digest_occurrences: dict[str, int] = {}
    for index, text in enumerate(text_chunks, start=1):
        digest = _content_digest(text)
        digest_occurrences[digest] = digest_occurrences.get(digest, 0) + 1
        chunk_id = _stable_chunk_id(
            document.doc_id,
            text,
            occurrence=digest_occurrences[digest],
        )
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                title=document.title,
                doc_type=document.doc_type,
                asset_type=document.asset_type,
                source=document.source,
                text=text,
                failure_category=document.failure_category,
                version=document.version,
                effective_date=document.effective_date,
                language=document.language,
                chunk_index=index,
            )
        )
    return chunks


def _split_by_section_markers(text: str) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
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
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if overlap < 0:
        raise ValueError("overlap must not be negative.")
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars.")
    safe_overlap = overlap
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
    for separator in ["\n", ". ", "; ", ", ", " "]:
        boundary = text.rfind(separator, minimum, end)
        if boundary != -1:
            return boundary + len(separator)
    return end


def _split_section(text: str, *, max_chars: int, overlap: int) -> list[str]:
    """Split one section while repeating its heading on every continuation chunk."""

    if len(text) <= max_chars:
        return [text]
    marker_pattern = "|".join(re.escape(marker) for marker in SECTION_MARKERS)
    heading_match = re.match(marker_pattern, text, flags=re.IGNORECASE)
    if not heading_match:
        return _split_long_text(text, max_chars=max_chars, overlap=overlap)
    heading = heading_match.group(0)
    body = text[heading_match.end() :].strip()
    body_budget = max_chars - len(heading) - 1
    if body_budget < 100:
        return _split_long_text(text, max_chars=max_chars, overlap=overlap)
    body_overlap = min(overlap, max(0, body_budget - 1))
    return [f"{heading}\n{part}" for part in _split_long_text(body, body_budget, body_overlap)]


def _content_digest(text: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(text.split()))
    return blake2b(normalized.encode("utf-8"), digest_size=12).hexdigest()


def _stable_chunk_id(doc_id: str, text: str, *, occurrence: int = 1) -> str:
    """Return a stable content-derived ID independent of unrelated section ordering."""

    suffix = f"-{occurrence}" if occurrence > 1 else ""
    return f"{doc_id}-chunk-{_content_digest(text)}{suffix}"
