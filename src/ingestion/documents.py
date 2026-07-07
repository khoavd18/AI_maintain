"""Document utilities for SOP, checklist, and ticket context ingestion."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    """A chunk of source text ready to embed and store."""

    source: str
    text: str
    chunk_index: int


def chunk_text(text: str, source: str, chunk_size: int = 800, overlap: int = 100) -> list[DocumentChunk]:
    """Split text into overlapping chunks for retrieval."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[DocumentChunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(DocumentChunk(source=source, text=chunk, chunk_index=index))
            index += 1
        if end == len(text):
            break
        start = end - overlap
    return chunks
