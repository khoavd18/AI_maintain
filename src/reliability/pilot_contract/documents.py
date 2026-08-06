"""JSON document loading and semantic manifest hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .constants import JsonSource

def load_json_document(source: JsonSource) -> dict[str, Any]:
    """Load a JSON object from a mapping or path."""

    if isinstance(source, Mapping):
        return json.loads(json.dumps(source))
    path = Path(source)
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return value


def manifest_sha256(manifest: JsonSource) -> str:
    """Return a stable SHA-256 over the semantic JSON manifest."""

    payload = load_json_document(manifest)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


