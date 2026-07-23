"""FastAPI routes for ticket intake, queues, SLA, and communication."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

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
from src.ticket_management.schemas import (
    BusinessCalendarRequest,
    BusinessCalendarResponse,
    BusinessCalendarUpdateRequest,
    EscalationEvaluationRequest,
    EscalationEvaluationResponse,
    PriorityPreviewResponse,
    SlaPolicyRequest,
    SlaPolicyResponse,
    SlaPolicyUpdateRequest,
    SlaSummaryResponse,
    TicketAssignRequest,
    TicketCommentRequest,
    TicketCommentResponse,
    TicketDetailResponse,
    TicketIntakeRequest,
    TicketOptionsResponse,
    TicketPriorityRequest,
    TicketQueuePage,
    TicketReasonAction,
    TicketResolveRequest,
    TicketSlaOverrideRequest,
    VersionedAction,
)
from src.ticket_management.service import (
    TicketAuthorizationError,
    TicketConflictError,
    TicketDomainError,
    TicketNotFoundError,
    TicketWorkflowService,
    build_ticket_workflow_service,
)

router = APIRouter()


@lru_cache(maxsize=1)
def get_ticket_workflow_service() -> TicketWorkflowService:
    return build_ticket_workflow_service()


ServiceDependency = Annotated[TicketWorkflowService, Depends(get_ticket_workflow_service)]
TicketsRead = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_READ))]
TicketsCreate = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_CREATE))]
TicketsAssign = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_ASSIGN))]
TicketsAcknowledge = Annotated[
    CurrentUser, Depends(require_permission(Permission.TICKETS_ACKNOWLEDGE))
]
TicketsExecute = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_EXECUTE))]
TicketsResolve = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_RESOLVE))]
TicketsClose = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_CLOSE))]
TicketsReopen = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_REOPEN))]
TicketsCancel = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_CANCEL))]
TicketsUpdate = Annotated[CurrentUser, Depends(require_permission(Permission.TICKETS_UPDATE))]
SlaRead = Annotated[CurrentUser, Depends(require_permission(Permission.SLA_POLICIES_READ))]
SlaManage = Annotated[CurrentUser, Depends(require_permission(Permission.SLA_POLICIES_MANAGE))]
EscalationEvaluate = Annotated[
    CurrentUser, Depends(require_permission(Permission.ESCALATIONS_EVALUATE))
]


@router.get(
    "/ticketing/options",
    response_model=TicketOptionsResponse,
    tags=["ticket operations"],
)
def ticket_options(service: ServiceDependency, actor: TicketsRead) -> dict[str, object]:
    return _handle(service.options, actor=actor)


@router.get(
    "/ticketing/priority-preview",
    response_model=PriorityPreviewResponse,
    tags=["ticket operations"],
)
def priority_preview(
    service: ServiceDependency,
    _actor: TicketsRead,
    impact: str,
    urgency: str,
) -> dict[str, str]:
    return _handle(service.priority_preview, impact=impact, urgency=urgency)


@router.post(
    "/tickets/intake",
    response_model=TicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ticket operations"],
)
def ticket_intake(
    payload: TicketIntakeRequest,
    service: ServiceDependency,
    request: Request,
    actor: TicketsCreate,
) -> dict[str, object]:
    return _handle(
        service.intake,
        request=payload.model_dump(mode="python"),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.get(
    "/ticket-queues/{queue_name}",
    response_model=TicketQueuePage,
    tags=["ticket operations"],
)
def ticket_queue(
    queue_name: str,
    service: ServiceDependency,
    actor: TicketsRead,
    asset_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None,
    category_id: UUID | None = None,
    support_group_id: UUID | None = None,
    assigned_user_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=200),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, object]:
    return _handle(
        service.list_queue,
        queue_name=queue_name,
        actor=actor,
        filters={
            "asset_id": asset_id,
            "status": status_filter,
            "priority": priority,
            "category_id": category_id,
            "support_group_id": support_group_id,
            "assigned_user_id": assigned_user_id,
            "search": search,
        },
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetailResponse,
    tags=["ticket operations"],
)
def ticket_detail(
    ticket_id: str, service: ServiceDependency, actor: TicketsRead
) -> dict[str, object]:
    return _handle(service.get_ticket, ticket_id=ticket_id, actor=actor)


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def assign_ticket(
    ticket_id: str,
    payload: TicketAssignRequest,
    service: ServiceDependency,
    request: Request,
    actor: TicketsAssign,
) -> dict[str, object]:
    return _handle(
        service.assign,
        ticket_id=ticket_id,
        **payload.model_dump(),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.post(
    "/tickets/{ticket_id}/acknowledge",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def acknowledge_ticket(
    ticket_id: str,
    payload: VersionedAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsAcknowledge,
) -> dict[str, object]:
    return _action(service.acknowledge, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/start",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def start_ticket(
    ticket_id: str,
    payload: VersionedAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsExecute,
) -> dict[str, object]:
    return _action(service.start, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/hold",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def hold_ticket(
    ticket_id: str,
    payload: TicketReasonAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsExecute,
) -> dict[str, object]:
    return _action(service.hold, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/resume",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def resume_ticket(
    ticket_id: str,
    payload: VersionedAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsExecute,
) -> dict[str, object]:
    return _action(service.resume, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/resolve",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def resolve_ticket(
    ticket_id: str,
    payload: TicketResolveRequest,
    service: ServiceDependency,
    request: Request,
    actor: TicketsResolve,
) -> dict[str, object]:
    return _action(service.resolve, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/close",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def close_ticket(
    ticket_id: str,
    payload: VersionedAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsClose,
) -> dict[str, object]:
    return _action(service.close, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/reopen",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def reopen_ticket(
    ticket_id: str,
    payload: TicketReasonAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsReopen,
) -> dict[str, object]:
    return _action(service.reopen, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/cancel",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def cancel_ticket(
    ticket_id: str,
    payload: TicketReasonAction,
    service: ServiceDependency,
    request: Request,
    actor: TicketsCancel,
) -> dict[str, object]:
    return _action(service.cancel, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/priority",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def change_ticket_priority(
    ticket_id: str,
    payload: TicketPriorityRequest,
    service: ServiceDependency,
    request: Request,
    actor: TicketsUpdate,
) -> dict[str, object]:
    return _action(service.change_priority, ticket_id, payload, service, request, actor)


@router.post(
    "/tickets/{ticket_id}/sla-policy",
    response_model=TicketDetailResponse,
    tags=["ticket actions"],
)
def override_ticket_sla(
    ticket_id: str,
    payload: TicketSlaOverrideRequest,
    service: ServiceDependency,
    request: Request,
    actor: SlaManage,
) -> dict[str, object]:
    return _action(service.override_sla_policy, ticket_id, payload, service, request, actor)


@router.get(
    "/tickets/{ticket_id}/comments",
    response_model=list[TicketCommentResponse],
    tags=["ticket communication"],
)
def ticket_comments(
    ticket_id: str, service: ServiceDependency, actor: TicketsRead
) -> list[dict[str, object]]:
    detail = _handle(service.get_ticket, ticket_id=ticket_id, actor=actor)
    return list(detail.get("comments", []))


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ticket communication"],
)
def add_ticket_comment(
    ticket_id: str,
    payload: TicketCommentRequest,
    service: ServiceDependency,
    request: Request,
    actor: TicketsRead,
) -> dict[str, object]:
    return _handle(
        service.add_comment,
        ticket_id=ticket_id,
        request=payload.model_dump(mode="python"),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.get(
    "/ticketing/business-calendars",
    response_model=list[BusinessCalendarResponse],
    tags=["SLA administration"],
)
def business_calendars(service: ServiceDependency, actor: SlaRead) -> list[dict[str, object]]:
    return _handle(service.list_calendars, actor=actor)


@router.post(
    "/ticketing/business-calendars",
    response_model=BusinessCalendarResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["SLA administration"],
)
def create_business_calendar(
    payload: BusinessCalendarRequest,
    service: ServiceDependency,
    request: Request,
    actor: SlaManage,
) -> dict[str, object]:
    return _handle(
        service.create_calendar,
        request=payload.model_dump(mode="python"),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.patch(
    "/ticketing/business-calendars/{calendar_id}",
    response_model=BusinessCalendarResponse,
    tags=["SLA administration"],
)
def update_business_calendar(
    calendar_id: UUID,
    payload: BusinessCalendarUpdateRequest,
    service: ServiceDependency,
    request: Request,
    actor: SlaManage,
) -> dict[str, object]:
    values = payload.model_dump(mode="python")
    expected_version = values.pop("expected_version")
    return _handle(
        service.update_calendar,
        calendar_id=calendar_id,
        request=values,
        expected_version=expected_version,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.get(
    "/ticketing/sla-policies",
    response_model=list[SlaPolicyResponse],
    tags=["SLA administration"],
)
def sla_policies(service: ServiceDependency, actor: SlaRead) -> list[dict[str, object]]:
    return _handle(service.list_policies, actor=actor)


@router.post(
    "/ticketing/sla-policies",
    response_model=SlaPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["SLA administration"],
)
def create_sla_policy(
    payload: SlaPolicyRequest,
    service: ServiceDependency,
    request: Request,
    actor: SlaManage,
) -> dict[str, object]:
    return _handle(
        service.create_policy,
        request=payload.model_dump(mode="python"),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.patch(
    "/ticketing/sla-policies/{policy_id}",
    response_model=SlaPolicyResponse,
    tags=["SLA administration"],
)
def update_sla_policy(
    policy_id: UUID,
    payload: SlaPolicyUpdateRequest,
    service: ServiceDependency,
    request: Request,
    actor: SlaManage,
) -> dict[str, object]:
    values = payload.model_dump(mode="python")
    expected_version = values.pop("expected_version")
    return _handle(
        service.update_policy,
        policy_id=policy_id,
        request=values,
        expected_version=expected_version,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


@router.get(
    "/ticketing/sla-summary",
    response_model=SlaSummaryResponse,
    tags=["SLA operations"],
)
def sla_summary(service: ServiceDependency, actor: SlaRead) -> dict[str, object]:
    return _handle(service.sla_summary, actor=actor)


@router.post(
    "/ticketing/escalations/evaluate",
    response_model=EscalationEvaluationResponse,
    tags=["SLA operations"],
)
def evaluate_escalations(
    payload: EscalationEvaluationRequest,
    service: ServiceDependency,
    request: Request,
    actor: EscalationEvaluate,
) -> dict[str, object]:
    if not payload.dry_run and not actor.has(Permission.ESCALATIONS_EXECUTE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền ghi escalation events.",
        )
    return _handle(
        service.evaluate_escalations,
        dry_run=payload.dry_run,
        as_of=payload.as_of,
        actor=actor,
        audit_context=audit_context(actor, request),
    )


def _action(function, ticket_id, payload, service, request, actor):
    del service
    return _handle(
        function,
        ticket_id=ticket_id,
        **payload.model_dump(mode="python"),
        actor=actor,
        audit_context=audit_context(actor, request),
    )


def _handle(function, **kwargs):
    try:
        return function(**kwargs)
    except (TicketNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TicketAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (
        TicketConflictError,
        StaleRecordError,
        DuplicateIdentifierError,
        IntegrityViolationError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TicketDomainError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
