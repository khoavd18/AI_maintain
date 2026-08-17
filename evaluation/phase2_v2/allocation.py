"""Deterministic allocation helpers for Phase 2 v2 quotas."""

from __future__ import annotations

from collections import Counter
from typing import Any

from evaluation.phase2_v2.dataset_spec import (
    CATEGORY_QUOTA,
    LANGUAGE_TARGET,
    RISK_TARGET,
    _ORIGINAL_CATEGORIES,
    _ORIGINAL_UNACCENTED,
)


def _category_slots(family_code: str) -> list[str]:
    original = list(_ORIGINAL_CATEGORIES[family_code])
    observed = Counter(original)
    remaining = [
        category for category, count in CATEGORY_QUOTA for _ in range(count - observed[category])
    ]
    return original + remaining


def _risk_slots(original: list[dict[str, Any]]) -> list[str]:
    preserved = [str(case["risk_level"]) for case in original]
    observed = Counter(preserved)
    return preserved + [
        risk for risk, count in RISK_TARGET.items() for _ in range(count - observed[risk])
    ]


def _language_slots(original: list[dict[str, Any]]) -> list[str]:
    preserved = [
        "vi_no_diacritics" if case["case_id"] in _ORIGINAL_UNACCENTED else "vi_diacritics"
        for case in original
    ]
    observed = Counter(preserved)
    return preserved + [
        language
        for language, count in LANGUAGE_TARGET.items()
        for _ in range(count - observed[language])
    ]
