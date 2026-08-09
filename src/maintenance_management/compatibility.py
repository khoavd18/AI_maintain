"""Historical preventive-maintenance builder compatibility seam."""

from __future__ import annotations

from src.composition.maintenance import build_maintenance_planning_service as _build


def build_maintenance_planning_service():
    """Delegate the historical builder to the outer composition root."""

    return _build()
