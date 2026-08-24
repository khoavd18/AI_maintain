"""Dependency-light Airflow callbacks that delegate durable audit writes."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any


_AUDIT_TIMEOUT_SECONDS = 30
_ERROR_MESSAGE_LIMIT = 1_000
_PASSWORD_PATTERN = re.compile(r"(?i)\b(password|passwd|pwd|token|secret)\s*[=:]\s*[^,\s;]+")
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@/\s]+@")

logger = logging.getLogger(__name__)


def _context_value(context: Mapping[str, Any], attribute: str, fallback: str) -> str:
    dag_run = context.get("dag_run")
    value = getattr(dag_run, attribute, None) if dag_run is not None else None
    return str(value or context.get(attribute) or fallback)


def _task_value(context: Mapping[str, Any], attribute: str, fallback: Any) -> Any:
    task_instance = context.get("task_instance") or context.get("ti")
    return getattr(task_instance, attribute, fallback) if task_instance is not None else fallback


def _sanitize_error(exception: object) -> str:
    message = " ".join(str(exception or "Airflow task failed without an exception.").split())
    message = _PASSWORD_PATTERN.sub(r"\1=<redacted>", message)
    message = _URI_CREDENTIAL_PATTERN.sub(r"\1<redacted>@", message)
    return message[:_ERROR_MESSAGE_LIMIT]


def _invoke_audit(arguments: list[str]) -> None:
    """Run the authoritative audit CLI without masking the original task outcome."""

    try:
        result = subprocess.run(
            [sys.executable, "-m", "data_platform.pipeline", *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=_AUDIT_TIMEOUT_SECONDS,
        )
        if result.returncode:
            logger.error("Pipeline audit command failed with exit code %s.", result.returncode)
    except Exception:
        logger.exception("Unable to invoke the pipeline audit command.")


def record_task_retry(context: Mapping[str, Any]) -> None:
    """Record one idempotent retry event using metadata-only callback context."""

    _invoke_audit(
        [
            "audit-retry",
            "--run-id",
            _context_value(context, "run_id", "unknown_run"),
            "--task-id",
            str(_task_value(context, "task_id", "unknown_task")),
            "--try-number",
            str(_task_value(context, "try_number", 0) or 0),
            "--error-message",
            _sanitize_error(context.get("exception")),
        ]
    )


def record_pipeline_failure(context: Mapping[str, Any]) -> None:
    """Record the terminal DAG failure while preserving the original exception."""

    exception = context.get("exception")
    _invoke_audit(
        [
            "audit-fail",
            "--run-id",
            _context_value(context, "run_id", "unknown_run"),
            "--task-id",
            str(_task_value(context, "task_id", "dag_run")),
            "--error-type",
            type(exception).__name__ if exception is not None else "DagRunFailure",
            "--error-message",
            _sanitize_error(exception),
        ]
    )


def record_domain_pipeline_failure(context: Mapping[str, Any]) -> None:
    """Record a terminal Stage 10 DAG failure in its independent audit table."""

    exception = context.get("exception")
    run_id = _context_value(context, "run_id", "unknown_run")
    task_id = str(_task_value(context, "task_id", "dag_run"))
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "data_platform.domain_pipeline",
                "audit-fail",
                "--run-id",
                run_id,
                "--step",
                task_id,
                "--error",
                _sanitize_error(exception),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=_AUDIT_TIMEOUT_SECONDS,
        )
        if result.returncode:
            logger.error("Domain pipeline audit command failed with exit code %s.", result.returncode)
    except Exception:
        logger.exception("Unable to invoke the domain pipeline audit command.")


def record_domain_task_retry(context: Mapping[str, Any]) -> None:
    """Persist one sanitized Stage 10 task retry without payloads or credentials."""

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "data_platform.domain_pipeline",
                "audit-retry",
                "--run-id",
                _context_value(context, "run_id", "unknown_run"),
                "--step",
                str(_task_value(context, "task_id", "unknown_task")),
                "--error",
                _sanitize_error(context.get("exception")),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=_AUDIT_TIMEOUT_SECONDS,
        )
        if result.returncode:
            logger.error("Domain retry audit command failed with exit code %s.", result.returncode)
    except Exception:
        logger.exception("Unable to invoke the domain retry audit command.")
