"""Shared dependencies and exception mapping for maintenance routes.

The route modules stay focused on HTTP contracts and named actions.  This
module owns the dependency aliases and the single mapping from maintenance
domain/storage errors to HTTP responses, while preserving the existing
``get_maintenance_planning_service`` and ``_handle`` imports for compatibility.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status

from src.asset_management.storage import AttachmentStorageError, AttachmentValidationError
from src.maintenance_management.service import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
    MaintenanceNotFoundError,
    MaintenancePlanningService,
    build_maintenance_planning_service,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    UnsupportedStorageOperationError,
)
from src.security.dependencies import require_permission
from src.security.permissions import Permission
from src.security.service import CurrentUser


@lru_cache(maxsize=1)
def get_maintenance_planning_service() -> MaintenancePlanningService:
    """Return the canonical maintenance service used by every route group."""

    return build_maintenance_planning_service()


ServiceDependency = Annotated[
    MaintenancePlanningService, Depends(get_maintenance_planning_service)
]

PlansRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_READ))
]
PlansCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_CREATE))
]
PlansUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_UPDATE))
]
PlansPause = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_PAUSE))
]
PlansArchive = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_PLANS_ARCHIVE))
]
TemplatesRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_READ))
]
TemplatesCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_CREATE))
]
TemplatesUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.CHECKLIST_TEMPLATES_UPDATE))
]
WorkOrdersRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_READ))
]
WorkOrdersCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_CREATE))
]
WorkOrdersAssign = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_ASSIGN))
]
WorkOrdersUpdate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_UPDATE))
]
WorkOrdersExecute = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_EXECUTE))
]
WorkOrdersComplete = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_COMPLETE))
]
WorkOrdersVerify = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_VERIFY))
]
WorkOrdersCancel = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_CANCEL))
]
WorkOrdersReopen = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDERS_REOPEN))
]
GenerationRun = Annotated[
    CurrentUser, Depends(require_permission(Permission.MAINTENANCE_GENERATION_RUN))
]
EvidenceRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_READ))
]
EvidenceCreate = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_CREATE))
]
EvidenceDelete = Annotated[
    CurrentUser, Depends(require_permission(Permission.WORK_ORDER_ATTACHMENTS_DELETE))
]


def _handle(function, *args, **kwargs):
    """Call a named service action and preserve the existing HTTP contract."""

    try:
        return function(*args, **kwargs)
    except MaintenanceAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (MaintenanceNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        MaintenanceConflictError,
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AttachmentValidationError, MaintenanceDomainError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except (
        AttachmentStorageError,
        StorageUnavailableError,
        UnsupportedStorageOperationError,
        RepositoryError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
