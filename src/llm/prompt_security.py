"""Conservative prompt-injection screening for questions and retrieved text."""

from __future__ import annotations

import re
import unicodedata

_INJECTION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"ignore\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+instructions?",
        r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
        r"(?:reveal|show|print|return|expose).{0,80}(?:system prompt|developer message|api[_ -]?key|credential|access token)",
        r"(?:you are|act as)\s+(?:chatgpt|the system|a developer)",
        r"(?:jailbreak|prompt injection|<\|system\|>|\[system\])",
        r"bỏ\s+qua.{0,60}(?:hướng dẫn|chỉ thị|yêu cầu).{0,30}(?:trước|hệ thống|nhà phát triển)",
        r"(?:tiết lộ|hiển thị|in ra|trả về).{0,80}(?:prompt hệ thống|khóa api|mật khẩu|token|thông tin đăng nhập)",
        r"(?:ghi đè|thay thế).{0,20}(?:hướng dẫn|chỉ thị)\s+(?:của\s+)?(?:hệ thống|nhà phát triển)",
    )
)
_FOLDED_INJECTION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"bo[\W_]+qua.{0,60}(?:huong[\W_]+dan|chi[\W_]+thi|yeu[\W_]+cau).{0,30}(?:truoc|he[\W_]+thong|nha[\W_]+phat[\W_]+trien)",
        r"(?:tiet[\W_]+lo|hien[\W_]+thi|in[\W_]+ra|tra[\W_]+ve).{0,80}(?:prompt[\W_]+he[\W_]+thong|khoa[\W_]+api|mat[\W_]+khau|token|thong[\W_]+tin[\W_]+dang[\W_]+nhap)",
        r"(?:ghi[\W_]+de|thay[\W_]+the).{0,20}(?:huong[\W_]+dan|chi[\W_]+thi)[\W_]+(?:cua[\W_]+)?(?:he[\W_]+thong|nha[\W_]+phat[\W_]+trien)",
    )
)
_UNSAFE_EXECUTION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"<\s*(?:tool_call|function_call|system|assistant)\b",
        r"(?:subprocess\.|os\.system\(|powershell(?:\.exe)?\b|cmd\.exe\b|rm\s+-rf\b)",
        r"\b(?:drop|truncate|alter)\s+(?:table|database)\b",
        r"\b(?:update|delete\s+from|insert\s+into)\b.{0,100}\b(?:tickets?|work_orders?)\b",
        r"\b(?:automatically\s+)?(?:create|close|resolve|complete).{0,80}\b(?:ticket|work order)\b",
    )
)


def contains_prompt_injection(text: str) -> bool:
    """Return true for explicit instruction-override or secret-exfiltration patterns."""

    normalized = " ".join(text.split())
    folded = _fold_accents(normalized)
    return any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS) or any(
        pattern.search(folded) for pattern in _FOLDED_INJECTION_PATTERNS
    )


def contains_unsafe_instruction(text: str) -> bool:
    """Detect prompt overrides plus embedded tool, shell, SQL, or state-change directives."""

    normalized = " ".join(text.split())
    return contains_prompt_injection(normalized) or any(
        pattern.search(normalized) for pattern in _UNSAFE_EXECUTION_PATTERNS
    )


def _fold_accents(text: str) -> str:
    """Fold only for security comparison; never return this representation to callers."""

    decomposed = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return unicodedata.normalize(
        "NFC",
        "".join(character for character in decomposed if unicodedata.category(character) != "Mn"),
    )
