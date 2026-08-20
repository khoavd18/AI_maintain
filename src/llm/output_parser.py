"""Parse and validate provider output without trusting provider-side schemas."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import ValidationError

from src.llm.base import LLMOutputError
from src.llm.models import ConversationalLLMAnswer, GroundedLLMAnswer
from src.llm.prompt_security import contains_unsafe_instruction

MAX_GENERATED_CONTENT_CHARS = 50000
_VIETNAMESE_SIGNAL_CHARACTERS = frozenset(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_MIN_VIETNAMESE_SIGNAL_TOKENS = 3
_MIN_VIETNAMESE_SIGNAL_RATIO = 0.2
_LANGUAGE_TOKEN_PATTERN = re.compile(r"[^\W\d_]+", flags=re.UNICODE)
_IRRELEVANT_LANGUAGE_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:s\d{1,3}|[a-z][a-z0-9._/-]*\d[a-z0-9._/-]*|\d+(?:[.,]\d+)?)\b"
)
_IGNORED_LANGUAGE_TOKENS = frozenset(
    {
        "a",
        "ac",
        "bar",
        "dc",
        "hz",
        "ka",
        "kg",
        "kpa",
        "kw",
        "ma",
        "mm",
        "mpa",
        "nm",
        "psi",
        "rpm",
        "v",
        "vac",
        "vdc",
    }
)
_VIETNAMESE_FOLDED_MARKERS = frozenset(
    {
        "bao",
        "bi",
        "bo",
        "bom",
        "buoc",
        "can",
        "chay",
        "chi",
        "cho",
        "cua",
        "dien",
        "dong",
        "duoc",
        "ghi",
        "hay",
        "hoac",
        "hoat",
        "huong",
        "kiem",
        "ket",
        "khi",
        "khong",
        "ky",
        "lanh",
        "lap",
        "loi",
        "may",
        "mo",
        "ngat",
        "nguyen",
        "nhan",
        "nguon",
        "neu",
        "noi",
        "phan",
        "phai",
        "phat",
        "qua",
        "sau",
        "siet",
        "tat",
        "theo",
        "thao",
        "thiet",
        "thuat",
        "thuc",
        "tra",
        "tri",
        "truoc",
        "va",
        "ve",
    }
)
_VIETNAMESE_FOLDED_PHRASES = frozenset(
    {
        "an toan",
        "bao tri",
        "bo phan",
        "chay thu",
        "ghi nhan",
        "hoat dong",
        "huong dan",
        "ket qua",
        "kiem tra",
        "khong duoc",
        "ky thuat",
        "may bom",
        "may lanh",
        "may phat",
        "nguyen nhan",
        "nguon dien",
        "noi tat",
        "sau khi",
        "thao lap",
        "thiet bi",
        "thuc hien",
        "truoc khi",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "after",
        "and",
        "before",
        "check",
        "condition",
        "equipment",
        "inspect",
        "measured",
        "must",
        "not",
        "of",
        "or",
        "power",
        "record",
        "restart",
        "should",
        "source",
        "terminal",
        "the",
        "then",
        "to",
        "verify",
        "voltage",
        "with",
    }
)
_ENGLISH_FUNCTION_MARKERS = frozenset(
    {"after", "and", "before", "must", "not", "of", "or", "should", "the", "then", "to", "with"}
)
ResponseLanguage = Literal["vi", "en", "mixed"]


def parse_grounded_answer(
    content: str,
    *,
    expected_language: ResponseLanguage = "vi",
) -> GroundedLLMAnswer:
    """Parse strict JSON and reject language-mismatched or prompt-leaking output."""

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
    if not _matches_expected_language(visible_text, expected_language):
        expected_label = {
            "vi": "tiếng Việt",
            "en": "tiếng Anh",
            "mixed": "ngôn ngữ hỗn hợp Việt-Anh",
        }[expected_language]
        raise LLMOutputError(f"Phản hồi LLM không đáp ứng yêu cầu {expected_label}.")
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
    tokens = _language_tokens(text)
    if not tokens:
        return False
    signal_tokens = sum(
        any(character in _VIETNAMESE_SIGNAL_CHARACTERS for character in token) for token in tokens
    )
    signal_ratio = signal_tokens / len(tokens)
    accented_vietnamese = (
        signal_tokens >= _MIN_VIETNAMESE_SIGNAL_TOKENS
        and signal_ratio >= _MIN_VIETNAMESE_SIGNAL_RATIO
    ) or (len(tokens) <= 8 and signal_tokens >= 2 and signal_ratio >= 0.4)
    if accented_vietnamese:
        return True

    folded_tokens = [_fold_language_token(token) for token in tokens]
    marker_occurrences = sum(token in _VIETNAMESE_FOLDED_MARKERS for token in folded_tokens)
    unique_markers = len(set(folded_tokens) & _VIETNAMESE_FOLDED_MARKERS)
    folded_text = f" {' '.join(folded_tokens)} "
    phrase_count = sum(f" {phrase} " in folded_text for phrase in _VIETNAMESE_FOLDED_PHRASES)
    return (
        len(tokens) >= 4
        and unique_markers >= 4
        and phrase_count >= 2
        and marker_occurrences / len(tokens) >= 0.35
    )


def _looks_like_english(text: str) -> bool:
    tokens = _language_tokens(text)
    if not tokens:
        return False
    folded_tokens = [_fold_language_token(token) for token in tokens]
    marker_occurrences = sum(token in _ENGLISH_MARKERS for token in folded_tokens)
    unique_markers = len(set(folded_tokens) & _ENGLISH_MARKERS)
    function_markers = sum(token in _ENGLISH_FUNCTION_MARKERS for token in folded_tokens)
    return (
        marker_occurrences >= 4
        and unique_markers >= 3
        and function_markers >= 2
        and marker_occurrences / len(tokens) >= 0.35
    )


def _looks_explicitly_mixed(text: str) -> bool:
    tokens = _language_tokens(text)
    if not tokens:
        return False
    folded_tokens = [_fold_language_token(token) for token in tokens]
    signal_tokens = sum(
        any(character in _VIETNAMESE_SIGNAL_CHARACTERS for character in token) for token in tokens
    )
    vietnamese_markers = sum(token in _VIETNAMESE_FOLDED_MARKERS for token in folded_tokens)
    english_markers = sum(token in _ENGLISH_MARKERS for token in folded_tokens)
    english_functions = sum(token in _ENGLISH_FUNCTION_MARKERS for token in folded_tokens)
    vietnamese_present = signal_tokens >= 2 and vietnamese_markers >= 3
    english_present = english_markers >= 4 and english_functions >= 2
    return vietnamese_present and english_present


def _matches_expected_language(text: str, expected_language: ResponseLanguage) -> bool:
    if expected_language == "vi":
        return _looks_like_vietnamese(text)
    if expected_language == "en":
        return _looks_like_english(text)
    if expected_language == "mixed":
        return _looks_explicitly_mixed(text)
    raise ValueError(f"Unsupported expected response language: {expected_language}")


def _language_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text).casefold()
    without_irrelevant = _IRRELEVANT_LANGUAGE_TOKEN_PATTERN.sub(" ", normalized)
    return [
        token
        for token in _LANGUAGE_TOKEN_PATTERN.findall(without_irrelevant)
        if token not in _IGNORED_LANGUAGE_TOKENS
    ]


def _fold_language_token(token: str) -> str:
    decomposed = unicodedata.normalize("NFD", token).replace("đ", "d")
    return "".join(character for character in decomposed if unicodedata.category(character) != "Mn")


def _strip_json_fence(content: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else content
