"""Evidence-link and UTC timestamp contracts shared by pilot records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .document_values import _is_placeholder
from .path_contracts import _looks_like_local_absolute_path, _url_contains_credentials


def _valid_evidence_links(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for link in value:
        if not isinstance(link, str) or not link.strip() or _is_placeholder(link):
            return False
        if _looks_like_local_absolute_path(link) or _url_contains_credentials(link):
            return False
    return True


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
