"""Deterministic model-applicability checks for selected asset context."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from src.rag.document_loader import canonicalize_document_revision_reference
from src.rag.retriever import RetrievalResult


_MODEL_IDENTIFIER_PATTERN = re.compile(
    r"\b(?P<family>[A-Za-z]{2,10})[\s._-]*(?P<number>\d{1,6}(?:[-_.]\d{1,6})?[A-Za-z]?)\b",
    flags=re.IGNORECASE,
)
_REVISION_REFERENCE_PATTERN = re.compile(
    r"\b(?:revision|rev|bản\s+in|phiên\s+bản)\s*[:#]?\s*"
    r"(?P<reference>\d{4}(?:[./-]\d{1,2})?(?:\s*[A-Za-z]{1,3})?|[A-Za-z]\d{5,})\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class ModelIdentifier:
    """One normalized technical model token and its alphabetic family."""

    family: str
    value: str


@dataclass(frozen=True)
class ApplicabilityConstraint:
    """Selected-model facts used for early and post-retrieval isolation."""

    selected_identifiers: tuple[ModelIdentifier, ...] = ()
    requested_identifiers: tuple[ModelIdentifier, ...] = ()
    requested_document_revision_reference: str = ""

    @property
    def question_conflicts_with_selected_model(self) -> bool:
        """Return true only for an explicit same-family, different-model request."""

        selected_by_family = _values_by_family(self.selected_identifiers)
        for requested in self.requested_identifiers:
            selected_values = selected_by_family.get(requested.family)
            if selected_values and requested.value not in selected_values:
                return True
        return False

    def allows(self, result: RetrievalResult) -> bool:
        """Reject explicit model or requested-document-revision conflicts."""

        if self.requested_document_revision_reference:
            if (
                not result.document_revision_reference
                or self.requested_document_revision_reference != result.document_revision_reference
            ):
                return False
        if not self.selected_identifiers:
            return True
        document_identifiers = _document_model_identifiers(result)
        if document_identifiers is None:
            return False
        document_by_family = _values_by_family(document_identifiers)
        selected_by_family = _values_by_family(self.selected_identifiers)
        for family, selected_values in selected_by_family.items():
            document_values = document_by_family.get(family)
            if document_values and selected_values.isdisjoint(document_values):
                return False
        return True


def build_applicability_constraint(
    question: str,
    asset_context: dict[str, Any] | None,
) -> ApplicabilityConstraint:
    """Resolve model tokens without inventing a manufacturer/model catalogue."""

    profile = (asset_context or {}).get("asset_profile") or {}
    selected_text = " ".join(str(profile.get(field) or "") for field in ("model", "model_scope"))
    return ApplicabilityConstraint(
        selected_identifiers=extract_model_identifiers(selected_text),
        requested_identifiers=extract_model_identifiers(question),
        requested_document_revision_reference=extract_requested_document_revision(question),
    )


def extract_model_identifiers(text: str) -> tuple[ModelIdentifier, ...]:
    """Extract identifiers such as CR 5, MLG15, and RZAG71-140N."""

    identifiers = {
        ModelIdentifier(
            family=match.group("family").upper(),
            value=re.sub(r"[^A-Za-z0-9]", "", match.group(0)).upper(),
        )
        for match in _MODEL_IDENTIFIER_PATTERN.finditer(text)
    }
    return tuple(sorted(identifiers))


def extract_requested_document_revision(question: str) -> str:
    """Return a revision only when the request names one with an explicit label."""

    match = _REVISION_REFERENCE_PATTERN.search(question)
    return canonicalize_document_revision_reference(match.group("reference")) if match else ""


def _document_model_identifiers(
    result: RetrievalResult,
) -> tuple[ModelIdentifier, ...] | None:
    """Prefer canonical source metadata; never concatenate provenance into a model token."""

    metadata_identifiers = extract_model_identifiers(" ".join(result.equipment_model_identifiers))
    text_identifiers = extract_model_identifiers(f"{result.title}\n{result.text}")
    if not metadata_identifiers:
        return text_identifiers

    metadata_by_family = _values_by_family(metadata_identifiers)
    text_by_family = _values_by_family(text_identifiers)
    for family, metadata_values in metadata_by_family.items():
        text_values = text_by_family.get(family)
        if text_values and metadata_values.isdisjoint(text_values):
            return None
    return metadata_identifiers


def _values_by_family(
    identifiers: tuple[ModelIdentifier, ...],
) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for identifier in identifiers:
        values.setdefault(identifier.family, set()).add(identifier.value)
    return values
