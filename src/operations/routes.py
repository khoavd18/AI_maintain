"""Authenticated notification and operator APIs for Product Milestone 7."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from src.config.settings import get_settings
from src.operations.schemas import (
    JobEnabledRequest,
    JobExecutionPage,
    LivenessResponse,
    ManualTriggerResponse,
    NotificationPage,
    NotificationResponse,
    NotificationVersionRequest,
    OperationalMetricsResponse,
    OperationalAlertEvaluationResponse,
    OutboxEventPage,
    OutboxRedriveResponse,
    ReadAllResponse,
    ReadinessResponse,
    ScheduledJobResponse,
    UnreadCountResponse,
    WorkerHealthResponse,
)
from src.operations.service import (
    OperationsAuthorizationError,
    OperationsService,
    build_operations_service,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    StaleRecordError,
    StorageUnavailableError,
)
from src.security.dependencies import audit_context, require_permission
from src.security.permissions import Permission
from src.security.service import CurrentUser

router = APIRouter()

ServiceDependency = Annotated[OperationsService, Depends(build_operations_service)]
NotificationsRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.NOTIFICATIONS_READ))
]
JobOperationsRead = Annotated[
    CurrentUser, Depends(require_permission(Permission.JOB_OPERATIONS_READ))
]
JobOperationsManage = Annotated[
    CurrentUser, Depends(require_permission(Permission.JOB_OPERATIONS_MANAGE))
]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=100,
        description="Caller-stable key for a manual trigger or retry.",
    ),
]


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["system"],
)
def liveness() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "alive",
        "release": settings.release_identity.as_dict(),
        "test_database_fingerprint": settings.test_database_fingerprint,
    }


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    tags=["system"],
)
def readiness(service: ServiceDependency) -> dict[str, object]:
    return _handle(service.readiness)


@router.get(
    "/health/worker",
    response_model=WorkerHealthResponse,
    tags=["system"],
)
def worker_health(
    service: ServiceDependency,
    response: Response,
) -> dict[str, object]:
    result = _handle(service.worker_health)
    if not result["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/notifications",
    response_model=NotificationPage,
    tags=["notifications"],
)
def list_notifications(
    service: ServiceDependency,
    actor: NotificationsRead,
    unread_only: bool = False,
    severity: str | None = Query(default=None, pattern="^(info|warning|critical)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    return _handle(
        service.list_notifications,
        actor=actor,
        unread_only=unread_only,
        severity=severity,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/notifications/unread-count",
    response_model=UnreadCountResponse,
    tags=["notifications"],
)
def unread_count(
    service: ServiceDependency, actor: NotificationsRead
) -> dict[str, int]:
    return _handle(service.unread_count, actor=actor)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    tags=["notifications"],
)
def mark_notification_read(
    notification_id: UUID,
    payload: NotificationVersionRequest,
    service: ServiceDependency,
    actor: NotificationsRead,
) -> dict[str, object]:
    return _handle(
        service.mutate_notification,
        notification_id=notification_id,
        action="read",
        expected_version=payload.expected_version,
        actor=actor,
    )


@router.post(
    "/notifications/{notification_id}/unread",
    response_model=NotificationResponse,
    tags=["notifications"],
)
def mark_notification_unread(
    notification_id: UUID,
    payload: NotificationVersionRequest,
    service: ServiceDependency,
    actor: NotificationsRead,
) -> dict[str, object]:
    return _handle(
        service.mutate_notification,
        notification_id=notification_id,
        action="unread",
        expected_version=payload.expected_version,
        actor=actor,
    )


@router.post(
    "/notifications/{notification_id}/dismiss",
    response_model=NotificationResponse,
    tags=["notifications"],
)
def dismiss_notification(
    notification_id: UUID,
    payload: NotificationVersionRequest,
    service: ServiceDependency,
    actor: NotificationsRead,
) -> dict[str, object]:
    return _handle(
        service.mutate_notification,
        notification_id=notification_id,
        action="dismiss",
        expected_version=payload.expected_version,
        actor=actor,
    )


@router.post(
    "/notifications/read-all",
    response_model=ReadAllResponse,
    tags=["notifications"],
)
def read_all_notifications(
    service: ServiceDependency, actor: NotificationsRead
) -> dict[str, int]:
    return _handle(service.read_all, actor=actor)


@router.get(
    "/operations/jobs",
    response_model=list[ScheduledJobResponse],
    tags=["job-operations"],
)
def list_jobs(
    service: ServiceDependency, actor: JobOperationsRead
) -> list[dict[str, object]]:
    return _handle(service.list_jobs, actor=actor)


@router.patch(
    "/operations/jobs/{job_key}",
    response_model=ScheduledJobResponse,
    tags=["job-operations"],
)
def set_job_enabled(
    job_key: str,
    payload: JobEnabledRequest,
    service: ServiceDependency,
    request: Request,
    actor: JobOperationsManage,
) -> dict[str, object]:
    return _handle(
        service.set_job_enabled,
        job_key=job_key,
        enabled=payload.enabled,
        expected_version=payload.expected_version,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.post(
    "/operations/jobs/{job_key}/trigger",
    response_model=ManualTriggerResponse,
    tags=["job-operations"],
)
def trigger_job(
    job_key: str,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    request: Request,
    actor: JobOperationsManage,
) -> dict[str, object]:
    return _handle(
        service.trigger_job,
        job_key=job_key,
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.post(
    "/operations/executions/{execution_id}/retry",
    response_model=ManualTriggerResponse,
    tags=["job-operations"],
)
def retry_execution(
    execution_id: UUID,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    request: Request,
    actor: JobOperationsManage,
) -> dict[str, object]:
    return _handle(
        service.retry_execution,
        execution_id=execution_id,
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.get(
    "/operations/executions",
    response_model=JobExecutionPage,
    tags=["job-operations"],
)
def list_executions(
    service: ServiceDependency,
    actor: JobOperationsRead,
    execution_status: str | None = Query(default=None, alias="status"),
    job_key: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    return _handle(
        service.list_executions,
        actor=actor,
        status=execution_status,
        job_key=job_key,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/operations/outbox",
    response_model=OutboxEventPage,
    tags=["job-operations"],
)
def list_outbox(
    service: ServiceDependency,
    actor: JobOperationsRead,
    outbox_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, object]:
    return _handle(
        service.list_outbox,
        actor=actor,
        status=outbox_status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/operations/outbox/{event_id}/retry",
    response_model=OutboxRedriveResponse,
    tags=["job-operations"],
)
def redrive_outbox_event(
    event_id: UUID,
    idempotency_key: IdempotencyKey,
    service: ServiceDependency,
    request: Request,
    actor: JobOperationsManage,
) -> dict[str, object]:
    return _handle(
        service.redrive_outbox_event,
        event_id=event_id,
        idempotency_key=idempotency_key,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.post(
    "/operations/alerts/evaluate",
    response_model=OperationalAlertEvaluationResponse,
    tags=["job-operations"],
)
def evaluate_operational_alerts(
    service: ServiceDependency,
    actor: JobOperationsManage,
) -> dict[str, int]:
    return _handle(service.evaluate_operational_alerts, actor=actor)


@router.get(
    "/operations/metrics",
    response_model=OperationalMetricsResponse,
    tags=["job-operations"],
)
def operational_metrics(
    service: ServiceDependency, actor: JobOperationsRead
) -> dict[str, object]:
    return _handle(service.metrics, actor=actor)


def _handle(function, **kwargs):
    try:
        return function(**kwargs)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationsAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
