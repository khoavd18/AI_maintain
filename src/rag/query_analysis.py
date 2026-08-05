"""Deterministic, testable analysis for focused maintenance questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.config.value_mappings import (
    ASSET_TYPE_CODE_TO_VI,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
)
from src.llm.prompt_security import contains_prompt_injection

QueryIntent = Literal[
    "preventive",
    "troubleshooting",
    "safety",
    "factual",
    "greeting",
    "identity",
    "capabilities",
    "courtesy",
    "unknown",
]
FOCUSED_ASSET_TYPES = frozenset(ASSET_TYPE_CODE_TO_VI.values())

_ASSET_ALIASES = {
    ASSET_TYPE_CODE_TO_VI["hvac"]: ("hvac", "máy lạnh", "điều hòa", "điều hoà"),
    ASSET_TYPE_CODE_TO_VI["pump"]: ("pump", "máy bơm", "bơm nước"),
    ASSET_TYPE_CODE_TO_VI["generator"]: ("generator", "máy phát điện", "máy phát"),
}
_UNSUPPORTED_TERMS = (
    "thang máy",
    "elevator",
    "tủ điện",
    "báo cháy",
    "bồn nước",
    "chiếu sáng",
    "xe máy",
    "ô tô",
)
_MAINTENANCE_TERMS = (
    "bảo trì",
    "bảo dưỡng",
    "kiểm tra",
    "sop",
    "checklist",
    "rủi ro",
    "bất thường",
    "rung",
    "ồn",
    "khởi động",
    "làm mát",
    "sự cố",
    "hỏng",
    "an toàn",
    "cảnh báo",
    "nguyên nhân",
)
_CONVERSATION_PHRASES: dict[QueryIntent, frozenset[str]] = {
    "greeting": frozenset(
        {
            "xin chào",
            "chào",
            "chào bạn",
            "chào trợ lý",
            "hello",
            "hello bạn",
            "hi",
            "hi bạn",
            "alo",
        }
    ),
    "identity": frozenset(
        {
            "bạn là ai",
            "bạn tên gì",
            "bạn là trợ lý gì",
            "đây là trợ lý gì",
            "xin chào bạn là ai",
            "chào bạn bạn là ai",
            "who are you",
            "what are you",
        }
    ),
    "capabilities": frozenset(
        {
            "bạn làm được gì",
            "bạn có thể làm gì",
            "bạn có thể giúp gì",
            "bạn giúp tôi được gì",
            "tôi có thể hỏi gì",
            "hướng dẫn sử dụng trợ lý",
            "what can you do",
        }
    ),
    "courtesy": frozenset(
        {
            "cảm ơn",
            "cảm ơn bạn",
            "xin cảm ơn",
            "thanks",
            "thank you",
            "tạm biệt",
            "chào tạm biệt",
            "bye",
            "goodbye",
        }
    ),
}
_CAPABILITY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        (
            r"^(?:bạn|trợ lý)\s+(?:có thể\s+)?"
            r"(?:cho\s+tôi\s+biết|giúp|hỗ\s+trợ|làm|trả\s+lời)"
            r"(?:\s+tôi)?(?:\s+được)?"
            r"(?:\s+(?:những\s+)?(?:thông\s+tin|nội\s+dung|việc))?\s+gì$"
        ),
        (
            r"^tôi\s+(?:có thể\s+)?hỏi(?:\s+bạn)?(?:\s+được)?"
            r"(?:\s+(?:những\s+)?(?:thông\s+tin|nội\s+dung))?\s+gì$"
        ),
    )
)
_UNSAFE_OPERATION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:run|execute|open)\s+(?:this\s+)?(?:shell|powershell|cmd|terminal|sql)\b",
        r"\b(?:rm\s+-rf|powershell(?:\.exe)?|cmd\.exe|subprocess\.|os\.system\()",
        r"\b(?:drop|truncate|alter)\s+(?:table|database)\b",
        r"\b(?:update|delete\s+from|insert\s+into)\b.{0,100}\b(?:ticket|work[_ -]?order|maintenance)\b",
        r"(?:hãy|vui lòng)\s+(?:tự động\s+)?(?:tạo|đóng|resolve|hoàn tất|phân công).{0,80}(?:ticket|work order|lệnh công việc)",
        r"\b(?:automatically\s+)?(?:create|close|resolve|complete|assign).{0,80}\b(?:ticket|work order)\b",
        r"(?:hãy|vui lòng)\s+(?:bật|tắt|khởi động|dừng)\s+(?:máy|thiết bị|hvac|bơm|máy phát)",
        r"\b(?:turn on|turn off|start|stop)\s+(?:the\s+)?(?:equipment|hvac|pump|generator)\b",
        r"(?:xác nhận|tuyên bố).{0,60}(?:đã bảo trì xong|chẩn đoán chắc chắn)",
    )
)


@dataclass(frozen=True)
class QueryAnalysis:
    """Security and routing facts derived without an LLM call."""

    status: str
    asset_type: str | None
    failure_category: str | None
    document_type: str | None
    intent: QueryIntent
    safety_related: bool
    follow_up_reference: bool


class QueryAnalyzer:
    """Analyze scope, equipment, intent, and prohibited actions deterministically."""

    def analyze(
        self,
        question: str,
        *,
        selected_asset_type: str | None = None,
    ) -> QueryAnalysis:
        normalized = question.casefold()
        asset_type = infer_asset_type(question)
        failure_category = infer_failure_category(question)
        document_type = infer_document_type(question)
        conversation_intent = infer_conversation_intent(question)
        intent = conversation_intent or infer_intent(question)
        safety_related = any(term in normalized for term in ("an toàn", "cảnh báo", "ppe", "loto"))
        follow_up = bool(
            re.search(
                r"\b(?:nguyên nhân thứ|bước đó|cảnh báo trước|phần trên|cái đó|thứ hai|what about|second cause|how do i check|same apply|previous warning)\b",
                normalized,
            )
        )

        status = "supported"
        if contains_prompt_injection(question):
            status = "prompt_injection"
        elif any(pattern.search(question) for pattern in _UNSAFE_OPERATION_PATTERNS):
            status = "unsafe_operation"
        elif conversation_intent is not None:
            status = "conversation"
        elif (
            any(term in normalized for term in _UNSUPPORTED_TERMS) and not asset_type
        ) or (selected_asset_type and selected_asset_type not in FOCUSED_ASSET_TYPES):
            status = "unsupported_asset_type"
        elif selected_asset_type and asset_type and selected_asset_type != asset_type:
            status = "asset_context_mismatch"
        elif not any(term in normalized for term in _MAINTENANCE_TERMS):
            status = "unrelated"
        elif not selected_asset_type and not asset_type:
            status = "missing_asset_context"
        return QueryAnalysis(
            status=status,
            asset_type=asset_type,
            failure_category=failure_category,
            document_type=document_type,
            intent=intent,
            safety_related=safety_related,
            follow_up_reference=follow_up,
        )


def infer_conversation_intent(question: str) -> QueryIntent | None:
    """Recognize a deliberately small social surface without opening general chat."""

    normalized = re.sub(r"\s+", " ", question.casefold()).strip(" \t\r\n.!?,;:")
    for intent, phrases in _CONVERSATION_PHRASES.items():
        if normalized in phrases:
            return intent
    if any(pattern.fullmatch(normalized) for pattern in _CAPABILITY_PATTERNS):
        return "capabilities"
    return None


def infer_asset_type(question: str) -> str | None:
    normalized = question.casefold()
    for asset_type, terms in _ASSET_ALIASES.items():
        if any(term in normalized for term in terms):
            return asset_type
    return None


def infer_failure_category(question: str) -> str | None:
    normalized = question.casefold()
    if any(term in normalized for term in ("không làm mát", "làm lạnh", "không lạnh")):
        return FAILURE_TYPE_CODE_TO_VI["cooling_issue"]
    if any(term in normalized for term in ("rung", "tiếng ồn", "ồn bất thường")):
        return FAILURE_TYPE_CODE_TO_VI["vibration_issue"]
    if any(term in normalized for term in ("không khởi động", "lỗi điện", "mất điện")):
        return FAILURE_TYPE_CODE_TO_VI["electrical_issue"]
    return None


def infer_document_type(question: str) -> str | None:
    normalized = question.casefold()
    if "bảo trì định kỳ" in normalized or "kiểm tra định kỳ" in normalized:
        return DOCUMENT_TYPE_CODE_TO_VI["checklist"]
    return None


def infer_intent(question: str) -> QueryIntent:
    normalized = question.casefold()
    if any(term in normalized for term in ("an toàn", "cảnh báo", "ppe", "loto")):
        return "safety"
    if any(term in normalized for term in ("định kỳ", "bảo dưỡng", "lịch bảo trì")):
        return "preventive"
    if any(term in normalized for term in ("sự cố", "hỏng", "rung", "ồn", "không ")):
        return "troubleshooting"
    if any(term in normalized for term in ("là gì", "bao nhiêu", "khi nào")):
        return "factual"
    return "unknown"


def normalize_document_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized in DOCUMENT_TYPE_CODE_TO_VI:
        return DOCUMENT_TYPE_CODE_TO_VI[normalized]
    if normalized in DOCUMENT_TYPE_CODE_TO_VI.values():
        return normalized
    raise ValueError(f"document_type không được hỗ trợ: {value}")


def normalize_failure_category(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized in FAILURE_TYPE_CODE_TO_VI:
        return FAILURE_TYPE_CODE_TO_VI[normalized]
    if normalized in FAILURE_TYPE_CODE_TO_VI.values():
        return normalized
    raise ValueError(f"failure_category không được hỗ trợ: {value}")
