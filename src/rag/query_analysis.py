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
from src.rag.text_normalization import NormalizedText, normalize_for_matching

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
    ASSET_TYPE_CODE_TO_VI["pump"]: ("pump", "máy bơm", "bơm nước", "bơm"),
    ASSET_TYPE_CODE_TO_VI["generator"]: (
        "generator",
        "genset",
        "máy phát điện",
        "máy phát",
    ),
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
    "khởi động",
    "làm mát",
    "sự cố",
    "hỏng",
    "an toàn",
    "cảnh báo",
    "nguyên nhân",
    "check",
    "xử lý",
    "khắc phục",
)
_SYMPTOM_PHRASES = (
    "chảy nước",
    "rò rỉ",
    "không lên nước",
    "không có nước",
    "không hút nước",
    "không có lưu lượng",
    "không nổ",
    "đề không nổ",
    "không đề được",
    "không khởi động",
    "ko khởi động",
    "khởi động không được",
    "không làm mát",
    "không lạnh",
    "nóng",
    "quá nhiệt",
    "mùi lạ",
    "mùi bất thường",
    "mùi khét",
    "kêu lạ",
    "tiếng động lạ",
    "âm thanh bất thường",
    "tiếng ồn",
    "rung",
    "mất áp",
    "mất áp suất",
    "cảnh báo lặp lại",
    "cảnh báo tái diễn",
)
_FOLLOW_UP_PHRASES = (
    "nguyên nhân thứ",
    "bước thứ",
    "bước đó",
    "cảnh báo trước",
    "phần trên",
    "cái đó",
    "cái này",
    "thứ hai",
    "còn nguyên nhân kia",
    "nguyên nhân kia",
    "what about",
    "second cause",
    "how do i check",
    "same apply",
    "previous warning",
)
_STANDALONE_FOLLOW_UP_UTTERANCES = frozenset({"tại sao", "tại sao vậy"})
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
_UNSAFE_FOLDED_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:hay|vui long)\s+(?:tu dong\s+)?(?:tao|dong|resolve|hoan tat|phan cong).{0,80}(?:ticket|work order|lenh cong viec)",
        r"\b(?:bat|tat|khoi dong|dung)\s+(?:may|thiet bi|hvac|bom|may phat)",
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
    symptom_present: bool
    follow_up_reference: bool


class QueryAnalyzer:
    """Analyze scope, equipment, intent, and prohibited actions deterministically."""

    def analyze(
        self,
        question: str,
        *,
        selected_asset_type: str | None = None,
        recent_intent: QueryIntent | None = None,
        has_follow_up_context: bool = False,
    ) -> QueryAnalysis:
        normalized = normalize_for_matching(question)
        asset_type = infer_asset_type(question)
        effective_asset_type = asset_type or selected_asset_type
        failure_category = infer_failure_category(question, asset_type=effective_asset_type)
        document_type = infer_document_type(question)
        conversation_intent = infer_conversation_intent(question)
        intent = conversation_intent or infer_intent(question)
        follow_up = infer_follow_up_reference(question)
        symptom_present = normalized.contains(*_SYMPTOM_PHRASES)
        if (
            follow_up
            and intent == "unknown"
            and recent_intent
            in {
                "preventive",
                "troubleshooting",
                "safety",
                "factual",
            }
        ):
            intent = recent_intent
        safety_related = normalized.contains("an toàn", "cảnh báo", "ppe", "loto")
        maintenance_relevant = _is_maintenance_relevant(
            normalized,
            asset_type=effective_asset_type,
            document_type=document_type,
            failure_category=failure_category,
            follow_up=follow_up and has_follow_up_context,
        )

        status = "supported"
        if contains_prompt_injection(question):
            status = "prompt_injection"
        elif any(pattern.search(question) for pattern in _UNSAFE_OPERATION_PATTERNS) or any(
            pattern.search(normalized.folded) for pattern in _UNSAFE_FOLDED_PATTERNS
        ):
            status = "unsafe_operation"
        elif conversation_intent is not None:
            status = "conversation"
        elif (normalized.contains(*_UNSUPPORTED_TERMS) and not asset_type) or (
            selected_asset_type and selected_asset_type not in FOCUSED_ASSET_TYPES
        ):
            status = "unsupported_asset_type"
        elif selected_asset_type and asset_type and selected_asset_type != asset_type:
            status = "asset_context_mismatch"
        elif not maintenance_relevant:
            status = "unrelated"
        elif not effective_asset_type:
            status = "missing_asset_context"
        return QueryAnalysis(
            status=status,
            asset_type=asset_type,
            failure_category=failure_category,
            document_type=document_type,
            intent=intent,
            safety_related=safety_related,
            symptom_present=symptom_present,
            follow_up_reference=follow_up,
        )


def infer_conversation_intent(question: str) -> QueryIntent | None:
    """Recognize a deliberately small social surface without opening general chat."""

    normalized = normalize_for_matching(question).exact.strip(" \t\r\n.!?,;:")
    for intent, phrases in _CONVERSATION_PHRASES.items():
        if normalized in phrases:
            return intent
    if any(pattern.fullmatch(normalized) for pattern in _CAPABILITY_PATTERNS):
        return "capabilities"
    return None


def infer_follow_up_reference(question: str) -> bool:
    """Recognize bounded referential language without treating a new subject as context."""

    normalized = normalize_for_matching(question)
    exact_utterance = normalized.exact.strip(" \t\r\n.!?,;:")
    folded_utterance = normalized.folded.strip(" \t\r\n.!?,;:")
    standalone = {
        representation
        for phrase in _STANDALONE_FOLLOW_UP_UTTERANCES
        for representation in (
            normalize_for_matching(phrase).exact,
            normalize_for_matching(phrase).folded,
        )
    }
    return (
        exact_utterance in standalone
        or folded_utterance in standalone
        or normalized.contains(*_FOLLOW_UP_PHRASES)
    )


def infer_asset_type(question: str) -> str | None:
    normalized = normalize_for_matching(question)
    for asset_type, terms in _ASSET_ALIASES.items():
        if normalized.contains(*terms):
            return asset_type
    return None


def infer_failure_category(question: str, *, asset_type: str | None = None) -> str | None:
    normalized = normalize_for_matching(question)
    if asset_type in {None, ASSET_TYPE_CODE_TO_VI["hvac"]} and normalized.contains(
        "không làm mát",
        "làm lạnh",
        "không lạnh",
        "chảy nước",
        "nước ngưng",
        "đóng băng",
        "nóng",
    ):
        return FAILURE_TYPE_CODE_TO_VI["cooling_issue"]
    if asset_type in {None, ASSET_TYPE_CODE_TO_VI["pump"]} and normalized.contains(
        "rung",
        "tiếng ồn",
        "ồn bất thường",
        "kêu lạ",
        "tiếng động lạ",
        "âm thanh bất thường",
        "cavitation",
    ):
        return FAILURE_TYPE_CODE_TO_VI["vibration_issue"]
    if asset_type in {None, ASSET_TYPE_CODE_TO_VI["generator"]} and normalized.contains(
        "không khởi động",
        "ko khởi động",
        "không nổ",
        "đề không nổ",
        "không đề được",
        "lỗi điện",
        "mất điện",
        "ắc quy",
    ):
        return FAILURE_TYPE_CODE_TO_VI["electrical_issue"]
    return None


def infer_document_type(question: str) -> str | None:
    normalized = normalize_for_matching(question)
    if normalized.contains("bảo trì định kỳ", "kiểm tra định kỳ", "checklist"):
        return DOCUMENT_TYPE_CODE_TO_VI["checklist"]
    return None


def infer_intent(question: str) -> QueryIntent:
    normalized = normalize_for_matching(question)
    if normalized.contains("an toàn", "cảnh báo", "ppe", "loto"):
        return "safety"
    if normalized.contains("định kỳ", "bảo dưỡng", "lịch bảo trì", "checklist"):
        return "preventive"
    if normalized.contains("sự cố", "hỏng", *_SYMPTOM_PHRASES):
        return "troubleshooting"
    if normalized.contains("là gì", "bao nhiêu", "khi nào"):
        return "factual"
    return "unknown"


def _is_maintenance_relevant(
    normalized: NormalizedText,
    *,
    asset_type: str | None,
    document_type: str | None,
    failure_category: str | None,
    follow_up: bool,
) -> bool:
    if normalized.contains(*_MAINTENANCE_TERMS, *_SYMPTOM_PHRASES):
        return True
    if document_type or failure_category:
        return True
    return bool(follow_up and asset_type)


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
