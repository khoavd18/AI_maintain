"""Load Vietnamese maintenance documents for RAG indexing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RAW_DOCUMENT_FILE = Path("data/raw/documents.csv")
DOCUMENT_COLUMNS = [
    "doc_id",
    "title",
    "doc_type",
    "asset_type",
    "source",
    "clean_text",
    "created_at",
]


class DocumentLoadError(ValueError):
    """Raised when maintenance documents cannot be loaded for indexing."""


@dataclass(frozen=True)
class MaintenanceDocument:
    """A source document row from documents.csv."""

    doc_id: str
    title: str
    doc_type: str
    asset_type: str
    source: str
    clean_text: str
    created_at: str


def load_documents(path: Path = RAW_DOCUMENT_FILE) -> list[MaintenanceDocument]:
    """Load RAG source documents from documents.csv."""

    if not path.exists():
        raise DocumentLoadError(f"Document file not found: {path}")

    frame = pd.read_csv(path)
    missing_columns = set(DOCUMENT_COLUMNS) - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise DocumentLoadError(f"documents.csv is missing required columns: {missing}")

    documents: list[MaintenanceDocument] = []
    for record in frame[DOCUMENT_COLUMNS].to_dict(orient="records"):
        clean_text = _as_text(record["clean_text"])
        if not clean_text:
            continue
        documents.append(
            MaintenanceDocument(
                doc_id=_as_text(record["doc_id"]),
                title=_as_text(record["title"]),
                doc_type=_as_text(record["doc_type"]),
                asset_type=_as_text(record["asset_type"]),
                source=_as_text(record["source"]),
                clean_text=clean_text,
                created_at=_as_text(record["created_at"]),
            )
        )

    if not documents:
        raise DocumentLoadError(f"No usable documents found in {path}")
    return documents


def _as_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()
