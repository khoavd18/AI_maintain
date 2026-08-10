"""Closed post-start check order, access expectations, and report value contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal


_OPERATOR_PERMISSIONS = frozenset(
    {
        "assets:read",
        "tickets:read",
        "work_orders:read",
        "inventory:read",
        "analytics:read",
        "notifications:read",
        "job_operations:read",
    }
)
_RESTRICTED_REQUIRED_PERMISSIONS = frozenset(
    {
        "assets:read",
        "notifications:read",
    }
)
_RESTRICTED_FORBIDDEN_PERMISSIONS = frozenset(
    {
        "analytics:read",
        "job_operations:read",
        "job_operations:manage",
    }
)
_CHECK_ORDER = (
    "unauthenticated_boundary",
    "release_and_readiness",
    "operator_authentication",
    "operator_session_refresh",
    "restricted_authentication",
    "rbac_boundary",
    "scheduled_jobs",
    "approved_data_reads",
    "analytics_availability",
    "notification_owner_isolation",
    "session_cleanup",
)


CheckStatus = Literal["passed", "failed", "not_executed"]
OverallStatus = Literal["passed", "failed"]


@dataclass(frozen=True, slots=True)
class PostStartCheck:
    name: str
    status: CheckStatus
    evidence_code: str


@dataclass(frozen=True, slots=True)
class PostStartReport:
    schema_version: int
    generated_at: str
    scope: str
    executed: bool
    host_approved: bool
    intended_host_claim: bool
    production_readiness_claim: bool
    transport_scope: Literal["https", "loopback_http_test"]
    release_identifier: str
    release_commit: str
    release_tag: str
    alembic_revision: str
    overall_status: OverallStatus
    checks: tuple[PostStartCheck, ...]
    observations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["checks"] = [asdict(check) for check in self.checks]
        value["observations"] = dict(self.observations)
        return value
