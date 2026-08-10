"""Post-start environment-file loading and required credential lookup."""

from __future__ import annotations

import os
from pathlib import Path

from src.reliability.environment_loader import (
    EnvironmentFileError,
    load_environment_file as _load_environment_file,
)
from .preflight import PostStartValidationError


def load_environment_file(path: Path) -> dict[str, str]:
    """Compatibility wrapper preserving the post-start exception type."""

    try:
        return _load_environment_file(path)
    except EnvironmentFileError as exc:
        raise PostStartValidationError(str(exc)) from None


def _environment_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise PostStartValidationError(
            "A required smoke credential environment variable is unavailable."
        )
    return value
