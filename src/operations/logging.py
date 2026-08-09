"""Small JSON logging layer with a strict operational field allow-list."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

SAFE_LOG_FIELDS = {
    "event",
    "request_id",
    "correlation_id",
    "worker_identity",
    "job_key",
    "execution_id",
    "outbox_event_id",
    "status",
    "attempt_number",
    "duration_ms",
    "http_method",
    "http_path",
    "http_status",
    "created_count",
    "processed_count",
    "recovered_count",
    "error_code",
}


class JsonLogFormatter(logging.Formatter):
    """Serialize only bounded metadata; messages never include exception traces."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": str(record.getMessage())[:500],
        }
        for field in SAFE_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = _safe_scalar(value)
        # ASCII transport avoids Windows redirected-stream encoding failures while
        # preserving Vietnamese text through standard JSON Unicode escapes.
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure the application root logger once per process."""

    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(handler, "_pm7_json_handler", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler._pm7_json_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    """Write one structured event while dropping non-allow-listed metadata."""

    extra = {"event": event[:100]}
    extra.update(
        {
            key: _safe_scalar(value)
            for key, value in fields.items()
            if key in SAFE_LOG_FIELDS and value is not None
        }
    )
    logger.log(level, message[:500], extra=extra)


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:200]
