from pathlib import Path

from src.database.models import (
    SupportGroup,
    TicketCategory,
    TicketIntakeSource,
    TicketSubcategory,
)
from src.repositories.contracts import TicketReferenceKind
from src.repositories.postgres.tickets.queries import _REFERENCE_MODELS


def test_ticket_reference_kind_has_only_supported_intake_references() -> None:
    assert _REFERENCE_MODELS == {
        TicketReferenceKind.CATEGORY: TicketCategory,
        TicketReferenceKind.SUBCATEGORY: TicketSubcategory,
        TicketReferenceKind.SUPPORT_GROUP: SupportGroup,
        TicketReferenceKind.INTAKE_SOURCE: TicketIntakeSource,
    }


def test_ticket_application_service_does_not_import_reference_orm_models() -> None:
    source = Path("src/ticket_management/service.py").read_text(encoding="utf-8")

    assert "from src.database.models import" not in source
    assert "TicketReferenceKind" in source
