"""Deterministically validate every model citation against supplied context."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata

from src.llm.models import GroundedLLMAnswer


@dataclass(frozen=True)
class CitationValidationResult:
    """Citation coverage result with no provider-controlled error text."""

    valid: bool
    cited_source_ids: tuple[str, ...]
    invalid_source_ids: tuple[str, ...]
    coverage_complete: bool
    support_complete: bool = True
    unsupported_claims: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "cited_source_ids": list(self.cited_source_ids),
            "invalid_source_ids": list(self.invalid_source_ids),
            "coverage_complete": self.coverage_complete,
            "support_complete": self.support_complete,
            "unsupported_claims": list(self.unsupported_claims),
        }


def validate_citations(
    answer: GroundedLLMAnswer,
    allowed_source_ids: set[str],
    source_text_by_id: dict[str, str] | None = None,
    minimum_token_overlap: float = 0.15,
) -> CitationValidationResult:
    """Require claim-level coverage and reject every unknown prompt-local ID."""

    citation_groups = [
        answer.summary_source_ids,
        *(item.source_ids for item in answer.possible_causes),
        *(item.source_ids for item in answer.recommended_checks),
        *(item.source_ids for item in answer.safety_warnings),
    ]
    claim_source_ids: set[str] = set()
    for group in citation_groups:
        claim_source_ids.update(group)
    declared_source_ids = set(answer.source_ids)
    coverage_complete = all(bool(group) for group in citation_groups) and (
        declared_source_ids == claim_source_ids
    )
    referenced_source_ids = declared_source_ids | claim_source_ids
    invalid = referenced_source_ids - allowed_source_ids
    unsupported_claims: list[str] = []
    if source_text_by_id is not None:
        claims = [
            ("summary", answer.summary, answer.summary_source_ids),
            *(
                (f"possible_causes[{index}]", item.text, item.source_ids)
                for index, item in enumerate(answer.possible_causes)
            ),
            *(
                (f"recommended_checks[{index}]", item.text, item.source_ids)
                for index, item in enumerate(answer.recommended_checks)
            ),
            *(
                (f"safety_warnings[{index}]", item.text, item.source_ids)
                for index, item in enumerate(answer.safety_warnings)
            ),
        ]
        for label, claim, source_ids in claims:
            cited_text = " ".join(source_text_by_id.get(source_id, "") for source_id in source_ids)
            if not _has_lexical_support(claim, cited_text, minimum_token_overlap):
                unsupported_claims.append(label)
    support_complete = not unsupported_claims
    return CitationValidationResult(
        valid=(coverage_complete and support_complete and bool(claim_source_ids) and not invalid),
        cited_source_ids=tuple(sorted(claim_source_ids, key=_citation_sort_key)),
        invalid_source_ids=tuple(sorted(invalid, key=_citation_sort_key)),
        coverage_complete=coverage_complete,
        support_complete=support_complete,
        unsupported_claims=tuple(unsupported_claims),
    )


def _citation_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value.removeprefix("S")), value
    except ValueError:
        return 10_000, value


_TOKEN_PATTERN = re.compile(r"[^\W\d_]+|[A-Za-z]+[-_.]?[0-9]+", flags=re.UNICODE)
_STOP_WORDS = frozenset(
    {
        "và",
        "là",
        "có",
        "thể",
        "được",
        "cần",
        "theo",
        "trong",
        "trước",
        "sau",
        "khi",
        "để",
        "một",
        "các",
        "thiết",
        "bị",
        "tại",
        "hiện",
        "trường",
        "thực",
        "hiện",
    }
)


def _has_lexical_support(claim: str, source: str, minimum_overlap: float) -> bool:
    """Conservative contradiction proxy; citation presence remains the primary gate."""

    claim_tokens = _meaningful_tokens(claim)
    source_tokens = _meaningful_tokens(source)
    if not claim_tokens or not source_tokens:
        return False
    overlap = claim_tokens & source_tokens
    required = max(1, math.ceil(min(len(claim_tokens), 8) * minimum_overlap))
    return len(overlap) >= required


def _meaningful_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    return {
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if len(token) >= 2 and token not in _STOP_WORDS
    }
