"""Historical Copilot factory compatibility seam."""

from __future__ import annotations

from functools import lru_cache

from src.rag.copilot import MaintenanceCopilot


@lru_cache(maxsize=1)
def get_copilot_service() -> MaintenanceCopilot:
    """Delegate Copilot graph construction to the outer composition root."""

    from src.composition.copilot import get_copilot_service as build

    return build()
