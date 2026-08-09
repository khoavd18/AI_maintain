"""Parse and validate provider output without trusting provider-side schemas."""

from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from src.llm.base import LLMOutputError
from src.llm.models import ConversationalLLMAnswer, GroundedLLMAnswer
from src.llm.prompt_security import contains_unsafe_instruction

MAX_GENERATED_CONTENT_CHARS = 50000
_VIETNAMESE_MAINTENANCE_TERMS = (
    "thiết bị",
    "kiểm tra",
    "bảo trì",
    "an toàn",
    "nguyên nhân",
    "kỹ thuật",
)
_VIETNAMESE_SIGNAL_CHARACTERS = frozenset(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_MIN_VIETNAMESE_SIGNAL_TOKENS = 3
_MIN_VIETNAMESE_SIGNAL_RATIO = 0.2


def parse_grounded_answer(content: str) -> GroundedLLMAnswer:
    """Parse strict JSON and reject non-Vietnamese or prompt-leaking output."""

    normalized = _strip_json_fence(content.strip())
    if not normalized or len(normalized) > MAX_GENERATED_CONTENT_CHARS:
        raise LLMOutputError("Phản hồi LLM trống hoặc vượt giới hạn cho phép.")
    try:
        answer = GroundedLLMAnswer.model_validate_json(normalized)
    except ValidationError as exc:
        raise LLMOutputError("Phản hồi LLM không khớp schema bắt buộc.") from exc

    visible_text = " ".join(
        [
            answer.summary,
            *(item.text for item in answer.possible_causes),
            *(item.text for item in answer.recommended_checks),
            *(item.text for item in answer.safety_warnings),
        ]
    ).casefold()
    if not _looks_like_vietnamese(visible_text):
        raise LLMOutputError("Phản hồi LLM không đáp ứng yêu cầu tiếng Việt.")
    if re.search(r"(?i)(system prompt|developer message|api[_ -]?key|access token)", visible_text):
        raise LLMOutputError("Phản hồi LLM chứa nội dung cấu hình nội bộ không được phép.")
    if contains_unsafe_instruction(visible_text):
        raise LLMOutputError("Phản hồi LLM chứa chỉ thị thực thi không được phép.")
    return answer


def parse_conversational_answer(content: str) -> ConversationalLLMAnswer:
    """Parse a bounded Vietnamese social response and screen unsafe output."""

    normalized = _strip_json_fence(content.strip())
    if not normalized or len(normalized) > 4000:
        raise LLMOutputError("Phản hồi hội thoại trống hoặc vượt giới hạn cho phép.")
    try:
        answer = ConversationalLLMAnswer.model_validate_json(normalized)
    except ValidationError as exc:
        raise LLMOutputError("Phản hồi hội thoại không khớp schema bắt buộc.") from exc

    visible_text = answer.answer.casefold()
    if not _looks_like_vietnamese(visible_text):
        raise LLMOutputError("Phản hồi hội thoại không đáp ứng yêu cầu tiếng Việt.")
    if re.search(r"(?i)(system prompt|developer message|api[_ -]?key|access token)", visible_text):
        raise LLMOutputError("Phản hồi hội thoại chứa nội dung nội bộ không được phép.")
    if contains_unsafe_instruction(visible_text):
        raise LLMOutputError("Phản hồi hội thoại chứa chỉ thị thực thi không được phép.")
    return answer


def _looks_like_vietnamese(text: str) -> bool:
    normalized = unicodedata.normalize("NFC", text)
    if not any(
        term in normalized
        for term in (
            *_VIETNAMESE_MAINTENANCE_TERMS,
            "xin chào",
            "chào bạn",
            "trợ lý",
            "cảm ơn",
            "tạm biệt",
        )
    ):
        return False
    tokens = re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE)
    if not tokens:
        return False
    signal_tokens = sum(
        any(character in _VIETNAMESE_SIGNAL_CHARACTERS for character in token) for token in tokens
    )
    return (
        signal_tokens >= _MIN_VIETNAMESE_SIGNAL_TOKENS
        and signal_tokens / len(tokens) >= _MIN_VIETNAMESE_SIGNAL_RATIO
    )


def _strip_json_fence(content: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else content
