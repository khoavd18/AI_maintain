"""Conservative prompt-injection screening for questions and retrieved text."""

from __future__ import annotations

import re

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
    return any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS)


def contains_unsafe_instruction(text: str) -> bool:
    """Detect prompt overrides plus embedded tool, shell, SQL, or state-change directives."""

    normalized = " ".join(text.split())
    return contains_prompt_injection(normalized) or any(
        pattern.search(normalized) for pattern in _UNSAFE_EXECUTION_PATTERNS
    )
