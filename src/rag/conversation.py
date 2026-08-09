"""Bounded structured context for safe follow-up questions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from src.llm.prompt_security import contains_unsafe_instruction
from src.rag.query_analysis import FOCUSED_ASSET_TYPES, normalize_failure_category

_SOURCE_ID_PATTERN = re.compile(r"^S[1-9][0-9]{0,2}$")
_ALLOWED_KEYS = {
    "recent_intent",
    "resolved_asset_type",
    "resolved_failure_category",
    "previous_source_ids",
    "previous_answer_summary",
}


@dataclass(frozen=True)
class ConversationContext:
    """Minimum previous-turn facts accepted by retrieval orchestration."""

    recent_intent: str | None = None
    resolved_asset_type: str | None = None
    resolved_failure_category: str | None = None
    previous_source_ids: tuple[str, ...] = ()
    previous_answer_summary: str = ""

    @property
    def unsafe(self) -> bool:
        return contains_unsafe_instruction(
            "\n".join(
                value
                for value in (
                    self.recent_intent,
                    self.resolved_asset_type,
                    self.resolved_failure_category,
                    self.previous_answer_summary,
                )
                if value
            )
        )


def parse_conversation_context(value: dict[str, Any] | None) -> ConversationContext | None:
    """Reject arbitrary history and return one validated bounded context object."""

    if value is None:
        return None
    unknown = set(value) - _ALLOWED_KEYS
    if unknown:
        raise ValueError("conversation_context contains unsupported fields.")
    recent_intent = _optional_text(value.get("recent_intent"), 40, "recent_intent")
    resolved_asset_type = _optional_text(
        value.get("resolved_asset_type"),
        80,
        "resolved_asset_type",
    )
    if resolved_asset_type and resolved_asset_type not in FOCUSED_ASSET_TYPES:
        raise ValueError("conversation_context resolved_asset_type is unsupported.")
    raw_failure = _optional_text(
        value.get("resolved_failure_category"),
        80,
        "resolved_failure_category",
    )
    resolved_failure_category = normalize_failure_category(raw_failure) if raw_failure else None
    previous_answer_summary = (
        _optional_text(
            value.get("previous_answer_summary"),
            600,
            "previous_answer_summary",
        )
        or ""
    )
    raw_source_ids = value.get("previous_source_ids") or []
    if not isinstance(raw_source_ids, list) or len(raw_source_ids) > 10:
        raise ValueError(
            "conversation_context previous_source_ids must be a list of at most 10 IDs."
        )
    source_ids: list[str] = []
    for source_id in raw_source_ids:
        if not isinstance(source_id, str) or not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError("conversation_context contains an invalid previous source ID.")
        if source_id not in source_ids:
            source_ids.append(source_id)
    return ConversationContext(
        recent_intent=recent_intent,
        resolved_asset_type=resolved_asset_type,
        resolved_failure_category=resolved_failure_category,
        previous_source_ids=tuple(source_ids),
        previous_answer_summary=previous_answer_summary,
    )


def _optional_text(value: Any, maximum: int, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"conversation_context {field} must be text.")
    normalized = " ".join(value.split())
    if len(normalized) > maximum:
        raise ValueError(f"conversation_context {field} exceeds its length limit.")
    return normalized or None
