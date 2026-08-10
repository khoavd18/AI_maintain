"""Contained atomic JSON evidence publication for post-start reports."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .contracts import PostStartReport
from .preflight import PostStartValidationError, _REPOSITORY_ROOT


def _validated_evidence_dir(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
        raise PostStartValidationError(
            "Raw post-start evidence must be written outside the repository."
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_report(root: Path, report: PostStartReport) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = root / f"pm9-post-start-validation-{stamp}.json"
    partial = destination.with_suffix(".partial")
    partial.write_text(
        json.dumps(
            report.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(partial, destination)
    return destination


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
