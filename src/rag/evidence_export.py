"""Bounded local eligibility/export contract for unstructured RAG evidence.

This module performs no vectorization, embedding, network, or model call.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


MAX_EVIDENCE_CANDIDATES = 10_000
MAX_EVIDENCE_TEXT_CHARS = 20_000
ELIGIBLE_EVIDENCE_TYPES = frozenset(
    {
        "manual",
        "sop",
        "resolution_summary",
        "technician_note",
        "failure_description",
    }
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)")


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_type: str
    source_id: str
    text: str
    source_updated_at: datetime | str | None
    provenance: dict[str, str]
    eligible: bool = True
    contains_sensitive_data: bool = False


@dataclass(frozen=True, slots=True)
class EligibleEvidence:
    evidence_id: str
    evidence_type: str
    source_id: str
    text: str
    source_updated_at: str | None
    provenance: dict[str, str]


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _eligible(candidate: EvidenceCandidate) -> bool:
    text = _normalized_text(candidate.text)
    return bool(
        candidate.eligible
        and not candidate.contains_sensitive_data
        and candidate.evidence_type in ELIGIBLE_EVIDENCE_TYPES
        and text
        and len(text) <= MAX_EVIDENCE_TEXT_CHARS
        and not _EMAIL_PATTERN.search(text)
        and not _PHONE_PATTERN.search(text)
    )


def collect_eligible_evidence(
    candidates: Iterable[EvidenceCandidate],
    *,
    max_candidates: int,
) -> list[EligibleEvidence]:
    """Filter, deduplicate, and bound deterministic local evidence."""

    if isinstance(max_candidates, bool) or not 1 <= max_candidates <= MAX_EVIDENCE_CANDIDATES:
        raise ValueError(
            f"max_candidates must be between 1 and {MAX_EVIDENCE_CANDIDATES}."
        )
    accepted: list[EligibleEvidence] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not _eligible(candidate):
            continue
        text = _normalized_text(candidate.text)
        fingerprint = sha256(
            f"{candidate.evidence_type}\n{text}".encode("utf-8")
        ).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        updated = candidate.source_updated_at
        accepted.append(
            EligibleEvidence(
                evidence_id=fingerprint,
                evidence_type=candidate.evidence_type,
                source_id=candidate.source_id,
                text=text,
                source_updated_at=(
                    updated.isoformat() if isinstance(updated, datetime) else updated
                ),
                provenance=dict(sorted(candidate.provenance.items())),
            )
        )
        if len(accepted) >= max_candidates:
            break
    return accepted


def iter_postgres_evidence(
    settings: DataPlatformSettings,
    *,
    scan_limit: int,
) -> Iterator[EvidenceCandidate]:
    """Read only allow-listed non-PII fields from the analytical source contract."""

    if not 1 <= scan_limit <= MAX_EVIDENCE_CANDIDATES * 4:
        raise ValueError("scan_limit exceeds the bounded evidence scan contract.")
    statement = """
        SELECT evidence_type, source_id, evidence_text, source_updated_at, source_relation
        FROM (
            SELECT
                'resolution_summary'::text AS evidence_type,
                t.ticket_id::text AS source_id,
                t.resolution_summary AS evidence_text,
                t.source_updated_at,
                'analytics_source.tickets'::text AS source_relation
            FROM analytics_source.tickets t
            WHERE t.resolution_summary IS NOT NULL
            UNION ALL
            SELECT
                'technician_note'::text,
                t.ticket_id::text,
                t.technician_note,
                t.source_updated_at,
                'analytics_source.tickets'::text
            FROM analytics_source.tickets t
            WHERE t.technician_note IS NOT NULL
            UNION ALL
            SELECT
                'failure_description'::text,
                w.work_order_id::text,
                w.description,
                w.updated_at AS source_updated_at,
                'analytics_source.work_orders'::text
            FROM analytics_source.work_orders w
            WHERE w.description IS NOT NULL
        ) evidence
        ORDER BY evidence_type, source_id
        LIMIT %(scan_limit)s::integer
    """
    with connect(settings.validated(), read_only=True) as connection:
        cursor = connection.execute(statement, {"scan_limit": scan_limit})
        for row in cursor:
            yield EvidenceCandidate(
                evidence_type=str(row[0]),
                source_id=str(row[1]),
                text=str(row[2]),
                source_updated_at=row[3],
                provenance={"source_relation": str(row[4]), "source_id": str(row[1])},
            )


def iter_local_documents(root: Path) -> Iterator[EvidenceCandidate]:
    """Yield bounded UTF-8 manual/SOP files under one declared local root."""

    resolved_root = root.resolve()
    for path in sorted(resolved_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        resolved = path.resolve()
        if resolved_root not in resolved.parents:
            continue
        text = resolved.read_text(encoding="utf-8")
        evidence_type = "sop" if "sop" in path.name.casefold() else "manual"
        yield EvidenceCandidate(
            evidence_type=evidence_type,
            source_id=path.relative_to(resolved_root).as_posix(),
            text=text,
            source_updated_at=datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
            provenance={"local_root": resolved_root.name, "relative_path": path.relative_to(resolved_root).as_posix()},
        )


def export_evidence_jsonl(
    candidates: Iterable[EvidenceCandidate],
    destination: Path,
    *,
    max_candidates: int,
) -> dict[str, Any]:
    """Write one deterministic local JSONL export with no external side effect."""

    evidence = collect_eligible_evidence(candidates, max_candidates=max_candidates)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for item in evidence:
            handle.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(destination)
    digest = sha256(destination.read_bytes()).hexdigest()
    return {
        "path": destination.as_posix(),
        "candidate_count": len(evidence),
        "sha256": digest,
        "embedding_calls": 0,
        "external_api_calls": 0,
    }


__all__ = [
    "ELIGIBLE_EVIDENCE_TYPES",
    "EligibleEvidence",
    "EvidenceCandidate",
    "MAX_EVIDENCE_CANDIDATES",
    "collect_eligible_evidence",
    "export_evidence_jsonl",
    "iter_local_documents",
    "iter_postgres_evidence",
]
