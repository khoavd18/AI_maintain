"""Narrow value contracts shared by operator reliability drills."""

from __future__ import annotations

import re


_OPAQUE_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _validate_opaque_label(value: str) -> None:
    if not _OPAQUE_LABEL_PATTERN.fullmatch(value):
        raise ValueError("Target label must be an opaque lowercase identifier.")
