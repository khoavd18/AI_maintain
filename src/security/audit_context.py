"""Pure value types shared by application and repository contracts."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AuditContext:
    """Identity and request correlation data for caller-owned audit writes."""

    actor_user_id: UUID
    actor_display_name: str
    request_id: str
