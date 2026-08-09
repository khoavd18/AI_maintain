"""Single release identity contract shared by runtime and deployment tooling."""

from __future__ import annotations

from dataclasses import asdict, dataclass

APPLICATION_VERSION = "0.1.0"
CANONICAL_SCHEMA_REVISION = "20260726_0008"


@dataclass(frozen=True)
class ReleaseIdentity:
    """Public, secret-free identity for one running application release."""

    identifier: str
    application_version: str
    git_commit: str
    git_tag: str
    alembic_revision: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)
