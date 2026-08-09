"""Storage-neutral authenticated principal types.

The principal is shared by HTTP dependencies, application services, CLIs, and
repositories.  Keeping it separate from authentication orchestration prevents
those consumers from importing the authentication service merely for a type.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.security.permissions import Permission, Role


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated user and the permissions granted for this request."""

    id: UUID
    username: str
    email: str | None
    display_name: str
    role: Role
    permissions: frozenset[Permission]
    technician_id: str | None
    is_active: bool
    version: int
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions
