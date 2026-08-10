"""Contained load-report directory validation and JSON persistence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import tempfile
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _validated_report_directory(output_dir: Path | None) -> Path:
    report_dir = (
        output_dir or Path(tempfile.gettempdir()) / "ai-maintenance-copilot-reliability"
    ).resolve()
    if report_dir == _REPOSITORY_ROOT or report_dir.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("Reliability reports must be written outside the repository.")
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
