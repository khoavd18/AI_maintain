"""Small application-level runtime dependencies for PM7 operations."""

from dataclasses import asdict, dataclass
from typing import Protocol

from src.release import (
    APPLICATION_VERSION,
    CANONICAL_SCHEMA_REVISION,
    ReleaseIdentity,
)


@dataclass(frozen=True)
class DatabasePoolMetrics:
    """A bounded snapshot of database-pool utilisation."""

    size: int
    checked_out: int
    overflow: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class DatabasePoolMetricsProvider(Protocol):
    """Provides pool state without exposing a database implementation."""

    def snapshot(self) -> DatabasePoolMetrics: ...


@dataclass(frozen=True)
class OperationsRuntimeContext:
    """Immutable public runtime data supplied by the composition root."""

    release_identity: ReleaseIdentity


DEFAULT_OPERATIONS_RUNTIME_CONTEXT = OperationsRuntimeContext(
    ReleaseIdentity(
        identifier="unconfigured",
        application_version=APPLICATION_VERSION,
        git_commit="",
        git_tag="",
        alembic_revision=CANONICAL_SCHEMA_REVISION,
    )
)
