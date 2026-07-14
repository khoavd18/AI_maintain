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
    failure_category: str = ""
    version: str = "1.0"
    effective_date: str = ""
    raw_text: str = ""

    @property
    def document_id(self) -> str:
        """Return the canonical document identifier."""

        return self.doc_id

    @property
    def document_type(self) -> str:
        """Return the canonical document type."""

        return self.doc_type

    @property
    def content(self) -> str:
        """Return structured source content, falling back to normalized text."""

        return self.raw_text or self.clean_text


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
    for record in frame.to_dict(orient="records"):
        clean_text = _as_text(record["clean_text"])
        if not clean_text:
            continue
        raw_text = _first_text(record.get("content"), record.get("raw_text"))
        title = _as_text(record["title"])
        doc_type = _as_text(record["doc_type"])
        created_at = _as_text(record["created_at"])
        documents.append(
            MaintenanceDocument(
                doc_id=_as_text(record["doc_id"]),
                title=title,
                doc_type=doc_type,
                asset_type=_as_text(record["asset_type"]),
                source=_as_text(record["source"]),
                clean_text=clean_text,
                created_at=created_at,
                failure_category=_as_text(record.get("failure_category"))
                or _infer_failure_category(title, doc_type),
                version=_as_text(record.get("version")) or "1.0",
                effective_date=_as_text(record.get("effective_date"))
                or _date_from_timestamp(created_at),
                raw_text=raw_text,
            )
        )

    if not documents:
        raise DocumentLoadError(f"No usable documents found in {path}")
    return documents


def _as_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _first_text(*values: object) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _date_from_timestamp(value: str) -> str:
    if not value:
        return ""
    return value[:10]


def _infer_failure_category(title: str, document_type: str) -> str:
    if document_type == "Danh sách kiểm tra":
        return ""

    normalized = title.casefold()
    if "không làm mát" in normalized or "làm lạnh" in normalized:
        return "Lỗi làm lạnh"
    if "rung" in normalized or "tiếng ồn" in normalized:
        return "Lỗi rung động"
    if "không khởi động" in normalized:
        return "Lỗi điện"
    return ""
