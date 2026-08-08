"""Neutral, bounded dotenv parsing shared by reliability commands."""

from __future__ import annotations

import re
from pathlib import Path


_ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class EnvironmentFileError(RuntimeError):
    """Raised when a pilot environment file violates the parser contract."""


def load_environment_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file without expansion or secret-bearing errors."""

    if not path.is_file():
        raise EnvironmentFileError("Pilot environment file is unavailable.")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvironmentFileError(
                f"Pilot environment line {line_number} is not NAME=VALUE."
            )
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _ENVIRONMENT_NAME_PATTERN.fullmatch(name):
            raise EnvironmentFileError(
                f"Pilot environment line {line_number} has an invalid name."
            )
        if name in values:
            raise EnvironmentFileError(
                f"Pilot environment variable {name} is declared more than once."
            )
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values
