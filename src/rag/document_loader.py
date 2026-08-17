"""Validate and load controlled maintenance documents for RAG indexing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import re
from typing import Any

import pandas as pd

from src.config.value_mappings import ASSET_TYPE_CODE_TO_VI
from src.llm.prompt_security import contains_unsafe_instruction

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
SUPPORTED_ASSET_TYPES = frozenset(ASSET_TYPE_CODE_TO_VI.values())
_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
_MODEL_IDENTITY_PATTERN = re.compile(
    r"\b[A-Za-z]{2,10}[\s._-]*\d{1,6}(?:[\s._-]*\d{1,6})?[A-Za-z]?\b",
    flags=re.IGNORECASE,
)
_SOURCE_MODEL_SEGMENT_PATTERN = re.compile(r"^[A-Za-z]{2,10}\d{1,6}[A-Za-z0-9._-]*$")
_SOURCE_REVISION_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ]{0,31}$")


class DocumentLoadError(ValueError):
    """Raised when maintenance documents cannot be loaded for indexing."""


class DocumentValidationError(DocumentLoadError):
    """Raised when one or more source records violate the ingestion contract."""

    def __init__(self, report: "DocumentValidationReport") -> None:
        self.report = report
        super().__init__(
            f"Document validation failed for {report.invalid_records} of "
            f"{report.total_records} records."
        )


@dataclass(frozen=True)
class DocumentValidationIssue:
    """One public-safe validation issue tied to a source row."""

    row_number: int
    document_id: str | None
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class DocumentValidationReport:
    """Structured result of validating a document source."""

    total_records: int
    valid_records: int
    invalid_records: int
    errors: tuple[DocumentValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "validation_errors": [asdict(error) for error in self.errors],
        }


@dataclass(frozen=True)
class ValidatedDocumentBatch:
    """Validated documents plus non-lossy validation diagnostics."""

    documents: tuple["MaintenanceDocument", ...]
    report: DocumentValidationReport


@dataclass(frozen=True)
class DocumentIdentityMetadata:
    """Canonical equipment-model and document-revision metadata for one source."""

    equipment_model_identifiers: tuple[str, ...] = ()
    document_revision_reference: str = ""


@dataclass(frozen=True)
class MaintenanceDocument:
    """A validated source document from the controlled knowledge corpus."""

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
    language: str = "vi"
    equipment_model_identifiers: tuple[str, ...] = ()
    document_revision_reference: str = ""

    def __post_init__(self) -> None:
        metadata = resolve_document_identity_metadata(
            source=self.source,
            equipment_model_identifiers=self.equipment_model_identifiers,
            document_revision_reference=self.document_revision_reference,
        )
        object.__setattr__(
            self, "equipment_model_identifiers", metadata.equipment_model_identifiers
        )
        object.__setattr__(
            self, "document_revision_reference", metadata.document_revision_reference
        )

    @property
    def document_id(self) -> str:
        return self.doc_id

    @property
    def document_type(self) -> str:
        return self.doc_type

    @property
    def content(self) -> str:
        return self.raw_text or self.clean_text


def load_documents(path: Path = RAW_DOCUMENT_FILE) -> list[MaintenanceDocument]:
    """Load only a fully valid document set; never silently drop invalid rows."""

    batch = validate_document_source(path)
    if batch.report.errors:
        raise DocumentValidationError(batch.report)
    if not batch.documents:
        raise DocumentLoadError(f"No usable documents found in {path}")
    return list(batch.documents)


def validate_document_source(path: Path = RAW_DOCUMENT_FILE) -> ValidatedDocumentBatch:
    """Validate every CSV record and return both valid records and all errors."""

    if not path.exists():
        raise DocumentLoadError(f"Document file not found: {path}")
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise DocumentLoadError(f"Could not parse document file: {path}") from exc

    documents: list[MaintenanceDocument] = []
    errors: list[DocumentValidationIssue] = []
    seen_document_ids: set[str] = set()
    for index, record in enumerate(frame.to_dict(orient="records"), start=2):
        document, row_errors = _validate_record(record, row_number=index)
        if document is not None and document.doc_id in seen_document_ids:
            row_errors.append(
                _issue(
                    index,
                    document.doc_id,
                    "document_id",
                    "duplicate_document_id",
                    "document_id must be unique within one ingestion source.",
                )
            )
            document = None
        if row_errors:
            errors.extend(row_errors)
            continue
        if document is None:  # Defensive: _validate_record always explains invalid rows.
            continue
        seen_document_ids.add(document.doc_id)
        documents.append(document)

    invalid_rows = {error.row_number for error in errors}
    report = DocumentValidationReport(
        total_records=len(frame),
        valid_records=len(documents),
        invalid_records=len(invalid_rows),
        errors=tuple(errors),
    )
    return ValidatedDocumentBatch(documents=tuple(documents), report=report)


def _validate_record(
    record: dict[str, Any],
    *,
    row_number: int,
) -> tuple[MaintenanceDocument | None, list[DocumentValidationIssue]]:
    document_id = _first_text(record.get("document_id"), record.get("doc_id"))
    title = _as_text(record.get("title"))
    document_type = _first_text(record.get("document_type"), record.get("doc_type"))
    asset_type = _normalize_asset_type(_as_text(record.get("asset_type")))
    source = _as_text(record.get("source"))
    raw_text = _first_text(record.get("content"), record.get("raw_text"))
    clean_text = _first_text(record.get("clean_text"), raw_text)
    created_at = _as_text(record.get("created_at"))
    version = _as_text(record.get("version")) or "1.0"
    effective_date = _as_text(record.get("effective_date")) or _date_from_timestamp(created_at)
    language = _as_text(record.get("language")) or "vi"
    failure_category = _as_text(record.get("failure_category")) or _infer_failure_category(
        title, document_type
    )

    errors: list[DocumentValidationIssue] = []
    required_values = {
        "document_id": document_id,
        "title": title,
        "document_type": document_type,
        "asset_type": asset_type,
        "source": source,
        "content": clean_text,
        "effective_date": effective_date,
    }
    for field, value in required_values.items():
        if not value:
            errors.append(
                _issue(
                    row_number,
                    document_id or None,
                    field,
                    "missing_required_field",
                    f"{field} is required.",
                )
            )
    original_asset_type = _as_text(record.get("asset_type"))
    if original_asset_type and not asset_type:
        errors.append(
            _issue(
                row_number,
                document_id or None,
                "asset_type",
                "unsupported_asset_type",
                "asset_type is outside the supported HVAC, pump, and generator scope.",
            )
        )
    if effective_date and not _is_iso_date(effective_date):
        errors.append(
            _issue(
                row_number,
                document_id or None,
                "effective_date",
                "invalid_date",
                "effective_date must be a valid ISO date.",
            )
        )
    if not _VERSION_PATTERN.fullmatch(version):
        errors.append(
            _issue(
                row_number,
                document_id or None,
                "version",
                "invalid_version",
                "version must use a numeric dotted version such as 1.0.",
            )
        )
    if not _LANGUAGE_PATTERN.fullmatch(language):
        errors.append(
            _issue(
                row_number,
                document_id or None,
                "language",
                "invalid_language",
                "language must be an IETF-style language tag such as vi or en-US.",
            )
        )
    content_for_security = "\n".join(value for value in (title, raw_text, clean_text) if value)
    if content_for_security and _contains_suspicious_document_content(content_for_security):
        errors.append(
            _issue(
                row_number,
                document_id or None,
                "content",
                "unsafe_instruction_content",
                "content contains instruction-override, tool, shell, or SQL-like directives.",
            )
        )
    if errors:
        return None, errors
    return (
        MaintenanceDocument(
            doc_id=document_id,
            title=title,
            doc_type=document_type,
            asset_type=asset_type,
            source=source,
            clean_text=clean_text,
            created_at=created_at or f"{effective_date}T00:00:00+00:00",
            failure_category=failure_category,
            version=version,
            effective_date=effective_date[:10],
            raw_text=raw_text,
            language=language,
            equipment_model_identifiers=_first_text(
                record.get("equipment_model_identity"),
                record.get("model_applicability"),
                record.get("model_scope"),
            ),
            document_revision_reference=_first_text(
                record.get("document_revision_reference"),
                record.get("document_revision"),
            ),
        ),
        [],
    )


def resolve_document_identity_metadata(
    *,
    source: str,
    equipment_model_identifiers: tuple[str, ...] | list[str] | str = (),
    document_revision_reference: str = "",
) -> DocumentIdentityMetadata:
    """Keep controlled source model tokens separate from provenance revision text."""

    source_model, source_revision = _controlled_source_identity(source)
    identifiers = canonicalize_equipment_model_identifiers(equipment_model_identifiers)
    return DocumentIdentityMetadata(
        equipment_model_identifiers=identifiers or source_model,
        document_revision_reference=canonicalize_document_revision_reference(
            document_revision_reference or source_revision
        ),
    )


def canonicalize_equipment_model_identifiers(
    value: tuple[str, ...] | list[str] | str,
) -> tuple[str, ...]:
    """Return exact, punctuation-insensitive model identifiers without prefix matching."""

    text = value if isinstance(value, str) else " ".join(str(item) for item in value)
    identifiers = {
        re.sub(r"[^A-Za-z0-9]", "", match.group(0)).upper()
        for match in _MODEL_IDENTITY_PATTERN.finditer(text)
    }
    return tuple(sorted(identifiers))


def canonicalize_document_revision_reference(value: str) -> str:
    """Canonicalize a document reference without interpreting it as a model token."""

    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def _controlled_source_identity(source: str) -> tuple[tuple[str, ...], str]:
    """Read only the bounded ``SRC-...-MODEL-REVISION`` metadata convention."""

    parts = source.strip().split("-")
    if len(parts) < 4 or parts[0].upper() != "SRC":
        return (), ""
    model_segment, revision_segment = parts[-2], parts[-1]
    if not _SOURCE_MODEL_SEGMENT_PATTERN.fullmatch(model_segment):
        return (), ""
    if not _SOURCE_REVISION_SEGMENT_PATTERN.fullmatch(revision_segment):
        return (), ""
    identifiers = canonicalize_equipment_model_identifiers(model_segment)
    return identifiers, revision_segment


def _issue(
    row_number: int,
    document_id: str | None,
    field: str,
    code: str,
    message: str,
) -> DocumentValidationIssue:
    return DocumentValidationIssue(
        row_number=row_number,
        document_id=document_id,
        field=field,
        code=code,
        message=message,
    )


def _normalize_asset_type(value: str) -> str:
    if value in ASSET_TYPE_CODE_TO_VI:
        return ASSET_TYPE_CODE_TO_VI[value]
    return value if value in SUPPORTED_ASSET_TYPES else ""


def _contains_suspicious_document_content(text: str) -> bool:
    return contains_unsafe_instruction(text)


def _as_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip() if value is not None else ""


def _first_text(*values: object) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _date_from_timestamp(value: str) -> str:
    return value[:10] if value else ""


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return len(value) >= 10


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
