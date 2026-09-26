"""Input validation and secret-safe audit formatting."""

from __future__ import annotations

import re


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_MESSAGE_LIMIT = 1_000
_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|token|secret)\s*[=:]\s*[^,\s;]+"
)
_URI_CREDENTIAL_PATTERN = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@/\s]+@"
)


def validate_run_id(run_id: str) -> str:
    """Validate a caller-stable run identifier used in paths and audit rows."""

    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("Stage 10 run ID contains unsupported characters.")
    return run_id


def sanitize_audit_message(message: object, *, limit: int = _MESSAGE_LIMIT) -> str:
    """Redact common credential forms and return one bounded log line."""

    value = " ".join(str(message or "").split())
    value = _SECRET_PATTERN.sub(r"\1=<redacted>", value)
    value = _URI_CREDENTIAL_PATTERN.sub(r"\1<redacted>@", value)
    return value[:limit]
