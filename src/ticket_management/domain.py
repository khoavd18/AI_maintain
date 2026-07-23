"""Canonical ticket-domain codes, labels, priority matrix, and transitions."""

from __future__ import annotations

from enum import StrEnum


class TicketStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REOPENED = "reopened"


class Impact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Urgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMEDIATE = "immediate"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CommentVisibility(StrEnum):
    INTERNAL = "internal"
    REQUESTER = "requester"


class SlaClockType(StrEnum):
    FIRST_RESPONSE = "first_response"
    RESOLUTION = "resolution"


class SlaClockStatus(StrEnum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    PAUSED = "paused"
    MET = "met"
    DUE_SOON = "due_soon"
    BREACHED = "breached"
    STOPPED = "stopped"


class EscalationRule(StrEnum):
    FIRST_RESPONSE_DUE_SOON = "first_response_due_soon"
    FIRST_RESPONSE_BREACHED = "first_response_breached"
    RESOLUTION_DUE_SOON = "resolution_due_soon"
    RESOLUTION_BREACHED = "resolution_breached"
    REPEATED_REOPEN = "repeated_reopen"
    CRITICAL_PRIORITY = "critical_priority"


class TicketQueue(StrEnum):
    ALL = "all"
    UNASSIGNED = "unassigned"
    ASSIGNED_TO_ME = "assigned_to_me"
    ASSIGNED_TO_QUEUE = "assigned_to_queue"
    CRITICAL = "critical"
    DUE_SOON = "due_soon"
    BREACHED = "breached"
    WAITING = "waiting"
    RECENTLY_RESOLVED = "recently_resolved"
    REOPENED = "reopened"


TICKET_STATUS_LABELS = {
    TicketStatus.OPEN: "Mới tiếp nhận",
    TicketStatus.ASSIGNED: "Đã phân công",
    TicketStatus.IN_PROGRESS: "Đang xử lý",
    TicketStatus.WAITING: "Đang chờ",
    TicketStatus.RESOLVED: "Đã giải quyết",
    TicketStatus.CLOSED: "Đã đóng",
    TicketStatus.CANCELLED: "Đã hủy",
    TicketStatus.REOPENED: "Mở lại",
}

IMPACT_LABELS = {
    Impact.LOW: "Thấp",
    Impact.MEDIUM: "Trung bình",
    Impact.HIGH: "Cao",
    Impact.CRITICAL: "Nghiêm trọng",
}

URGENCY_LABELS = {
    Urgency.LOW: "Thấp",
    Urgency.MEDIUM: "Trung bình",
    Urgency.HIGH: "Cao",
    Urgency.IMMEDIATE: "Ngay lập tức",
}

PRIORITY_LABELS = {
    TicketPriority.LOW: "Thấp",
    TicketPriority.MEDIUM: "Trung bình",
    TicketPriority.HIGH: "Cao",
    TicketPriority.CRITICAL: "Khẩn cấp",
}

COMMENT_VISIBILITY_LABELS = {
    CommentVisibility.INTERNAL: "Ghi chú nội bộ",
    CommentVisibility.REQUESTER: "Cập nhật cho người yêu cầu",
}

SLA_STATUS_LABELS = {
    SlaClockStatus.NOT_STARTED: "Chưa áp dụng",
    SlaClockStatus.ACTIVE: "Đang chạy",
    SlaClockStatus.PAUSED: "Tạm dừng",
    SlaClockStatus.MET: "Đạt SLA",
    SlaClockStatus.DUE_SOON: "Sắp đến hạn",
    SlaClockStatus.BREACHED: "Vi phạm SLA",
    SlaClockStatus.STOPPED: "Đã dừng",
}

ESCALATION_RULE_LABELS = {
    EscalationRule.FIRST_RESPONSE_DUE_SOON: "First-response SLA sắp đến hạn",
    EscalationRule.FIRST_RESPONSE_BREACHED: "First-response SLA đã vi phạm",
    EscalationRule.RESOLUTION_DUE_SOON: "Resolution SLA sắp đến hạn",
    EscalationRule.RESOLUTION_BREACHED: "Resolution SLA đã vi phạm",
    EscalationRule.REPEATED_REOPEN: "Ticket mở lại nhiều lần",
    EscalationRule.CRITICAL_PRIORITY: "Ticket ưu tiên khẩn cấp",
}

TICKET_QUEUE_LABELS = {
    TicketQueue.ALL: "Tất cả ticket",
    TicketQueue.UNASSIGNED: "Chưa phân công",
    TicketQueue.ASSIGNED_TO_ME: "Phân công cho tôi",
    TicketQueue.ASSIGNED_TO_QUEUE: "Theo nhóm hỗ trợ",
    TicketQueue.CRITICAL: "Ưu tiên khẩn cấp",
    TicketQueue.DUE_SOON: "SLA sắp đến hạn",
    TicketQueue.BREACHED: "Đã vi phạm SLA",
    TicketQueue.WAITING: "Đang chờ",
    TicketQueue.RECENTLY_RESOLVED: "Mới giải quyết",
    TicketQueue.REOPENED: "Đã mở lại",
}

ASSIGNABLE_STATUSES = frozenset(
    {
        TicketStatus.OPEN,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING,
        TicketStatus.REOPENED,
    }
)

# Explicit matrix is the only authoritative priority calculation.
PRIORITY_MATRIX: dict[Impact, dict[Urgency, TicketPriority]] = {
    Impact.LOW: {
        Urgency.LOW: TicketPriority.LOW,
        Urgency.MEDIUM: TicketPriority.LOW,
        Urgency.HIGH: TicketPriority.MEDIUM,
        Urgency.IMMEDIATE: TicketPriority.HIGH,
    },
    Impact.MEDIUM: {
        Urgency.LOW: TicketPriority.LOW,
        Urgency.MEDIUM: TicketPriority.MEDIUM,
        Urgency.HIGH: TicketPriority.HIGH,
        Urgency.IMMEDIATE: TicketPriority.HIGH,
    },
    Impact.HIGH: {
        Urgency.LOW: TicketPriority.MEDIUM,
        Urgency.MEDIUM: TicketPriority.HIGH,
        Urgency.HIGH: TicketPriority.HIGH,
        Urgency.IMMEDIATE: TicketPriority.CRITICAL,
    },
    Impact.CRITICAL: {
        Urgency.LOW: TicketPriority.HIGH,
        Urgency.MEDIUM: TicketPriority.HIGH,
        Urgency.HIGH: TicketPriority.CRITICAL,
        Urgency.IMMEDIATE: TicketPriority.CRITICAL,
    },
}

LEGACY_PRIORITY_DIMENSIONS = {
    TicketPriority.LOW: (Impact.LOW, Urgency.LOW),
    TicketPriority.MEDIUM: (Impact.MEDIUM, Urgency.MEDIUM),
    TicketPriority.HIGH: (Impact.HIGH, Urgency.HIGH),
    TicketPriority.CRITICAL: (Impact.CRITICAL, Urgency.IMMEDIATE),
}

LEGACY_STATUS_LABELS = {
    TicketStatus.OPEN: "Mới tạo",
    TicketStatus.ASSIGNED: "Mới tạo",
    TicketStatus.REOPENED: "Mới tạo",
    TicketStatus.IN_PROGRESS: "Đang xử lý",
    TicketStatus.WAITING: "Đang xử lý",
    TicketStatus.RESOLVED: "Đã xử lý",
    TicketStatus.CLOSED: "Đã xử lý",
    TicketStatus.CANCELLED: "Đã xử lý",
}

ACTIVE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.OPEN,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING,
        TicketStatus.REOPENED,
    }
)


def calculate_priority(impact: str | Impact, urgency: str | Urgency) -> TicketPriority:
    """Return the deterministic matrix result for one impact/urgency pair."""

    return PRIORITY_MATRIX[Impact(impact)][Urgency(urgency)]


def legacy_priority_dimensions(
    priority: str | TicketPriority,
) -> tuple[Impact, Urgency]:
    """Map the legacy priority-only contract to a deterministic matrix diagonal."""

    return LEGACY_PRIORITY_DIMENSIONS[TicketPriority(priority)]


def priority_matrix_values() -> list[dict[str, str]]:
    """Expose the backend-owned matrix to clients without duplicating it."""

    return [
        {
            "impact": impact.value,
            "urgency": urgency.value,
            "priority": priority.value,
            "priority_display": PRIORITY_LABELS[priority],
        }
        for impact, row in PRIORITY_MATRIX.items()
        for urgency, priority in row.items()
    ]
