"""Integrity helpers for the Phase 2 v2 dataset builder."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_text(path: Path, value: str) -> None:
    path.write_bytes(value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def _assert_build_quotas(cases: list[dict[str, Any]]) -> None:
    assert len(cases) == 300
    assert Counter(case["case_id"].split("-")[1] for case in cases) == {
        "PUMP": 100,
        "HVAC": 100,
        "GEN": 100,
    }
    assert Counter(case["risk_level"] for case in cases) == {
        "critical": 45,
        "high": 75,
        "medium": 105,
        "low": 75,
    }
    assert Counter(case["language_variant"] for case in cases) == {
        "vi_diacritics": 180,
        "vi_no_diacritics": 45,
        "en": 45,
        "mixed_vi_en": 30,
    }
    assert Counter(case["response_policy"] for case in cases) == {
        "answer_with_evidence": 240,
        "refuse_insufficient_evidence": 30,
        "escalate_manual_review": 30,
    }
    assert sum(bool(case["adversarial_unsafe"]) for case in cases) == 30


def _write_checksums(dataset_dir: Path) -> None:
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(dataset_dir.iterdir(), key=lambda item: item.name.casefold())
        if path.is_file() and path.name != "checksums.sha256"
    ]
    _write_text(dataset_dir / "checksums.sha256", "\n".join(entries) + "\n")
