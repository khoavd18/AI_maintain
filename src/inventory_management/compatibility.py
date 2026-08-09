"""Historical inventory builder compatibility seam."""

from __future__ import annotations

from src.composition.inventory import build_inventory_management_service as _build


def build_inventory_management_service():
    """Delegate the historical builder to the outer composition root."""

    return _build()
