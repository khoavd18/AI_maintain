"""Historical ticket builder compatibility seam."""

from __future__ import annotations

from src.composition.tickets import build_ticket_workflow_service as _build


def build_ticket_workflow_service():
    """Delegate the historical builder to the outer composition root."""

    return _build()
