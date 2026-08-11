"""Conservative guards for exact high-risk maintenance parameter requests."""

from __future__ import annotations

import re
import unicodedata

from src.rag.text_normalization import normalize_for_matching


_FASTENER_SIZE_PATTERN = re.compile(r"(?<![A-Za-z0-9])m\s*\d{1,3}(?![A-Za-z0-9])", re.IGNORECASE)
_EXACT_PARAMETER_CUE_PATTERN = re.compile(
    r"(?<!\w)(?:bao nhiêu|bao nhieu|chính xác|chinh xac|cụ thể bao nhiêu|"
    r"cu the bao nhieu|phải dùng|phai dung|exact|exactly)(?!\w)",
    flags=re.IGNORECASE,
)
_PARAMETER_TERMS: dict[str, tuple[str, ...]] = {
    "torque": ("mô-men", "mô men", "torque", "siết", "nm"),
    "oil_grade": ("dầu", "độ nhớt", "sae"),
    "refrigerant": ("môi chất lạnh", "refrigerant", "nạp gas", "gas lạnh"),
    "electrical": ("điện áp", "dòng điện", "ampere", "voltage", "current"),
    "fuel": ("nhiên liệu", "diesel", "fuel"),
    "pressure": ("áp suất", "pressure", "psi", "kpa", "bar"),
    "rotating_speed": ("tốc độ quay", "vòng/phút", "rpm"),
}


def missing_exact_parameter_context(question: str) -> str | None:
    """Return a generic missing-context category for unsafe exact-value requests."""

    normalized = normalize_for_matching(question)
    exact_text = unicodedata.normalize("NFC", question).casefold()
    if not _EXACT_PARAMETER_CUE_PATTERN.search(exact_text):
        return None
    category = next(
        (name for name, terms in _PARAMETER_TERMS.items() if normalized.contains(*terms)),
        None,
    )
    if category is None:
        return None
    if category == "torque" and _FASTENER_SIZE_PATTERN.search(normalized.folded):
        return None
    return category
