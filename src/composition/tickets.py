"""Construction of the ticket workflow service graph."""

from __future__ import annotations

from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.postgres_tickets import PostgresTicketRepository


def build_ticket_workflow_service():
    """Build the canonical ticket service with a shared cached session factory."""

    settings = get_settings()
    from src.ticket_management.service import TicketWorkflowService

    return TicketWorkflowService(
        PostgresTicketRepository(get_session_factory(settings.database_url))
    )
