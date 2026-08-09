"""Canonical maintenance-planning codes, labels, and state transitions."""

from __future__ import annotations

from enum import StrEnum


class IntervalUnit(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class PlanStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ChecklistTemplateStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ChecklistResponseType(StrEnum):
    CHECKBOX = "checkbox"
    PASS_FAIL = "pass_fail"
    NUMERIC = "numeric"
    TEXT = "text"


class ChecklistResultStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class WorkOrderType(StrEnum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    INSPECTION = "inspection"
    EMERGENCY = "emergency"


class WorkOrderStatus(StrEnum):
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


PLAN_STATUS_LABELS = {
    PlanStatus.ACTIVE: "Đang hoạt động",
    PlanStatus.PAUSED: "Tạm dừng",
    PlanStatus.ARCHIVED: "Đã lưu trữ",
}
INTERVAL_UNIT_LABELS = {
    IntervalUnit.DAY: "ngày",
    IntervalUnit.WEEK: "tuần",
    IntervalUnit.MONTH: "tháng",
    IntervalUnit.YEAR: "năm",
}
WORK_ORDER_TYPE_LABELS = {
    WorkOrderType.PREVENTIVE: "Bảo trì phòng ngừa",
    WorkOrderType.CORRECTIVE: "Bảo trì sửa chữa",
    WorkOrderType.INSPECTION: "Kiểm tra",
    WorkOrderType.EMERGENCY: "Khẩn cấp",
}
WORK_ORDER_STATUS_LABELS = {
    WorkOrderStatus.PLANNED: "Đã lập kế hoạch",
    WorkOrderStatus.ASSIGNED: "Đã phân công",
    WorkOrderStatus.IN_PROGRESS: "Đang thực hiện",
    WorkOrderStatus.ON_HOLD: "Tạm giữ",
    WorkOrderStatus.COMPLETED: "Đã hoàn thành",
    WorkOrderStatus.VERIFIED: "Đã xác minh",
    WorkOrderStatus.CANCELLED: "Đã hủy",
}
CHECKLIST_RESPONSE_TYPE_LABELS = {
    ChecklistResponseType.CHECKBOX: "Xác nhận",
    ChecklistResponseType.PASS_FAIL: "Đạt / Không đạt",
    ChecklistResponseType.NUMERIC: "Giá trị số",
    ChecklistResponseType.TEXT: "Ghi chú",
}
CHECKLIST_RESULT_LABELS = {
    ChecklistResultStatus.PENDING: "Chưa thực hiện",
    ChecklistResultStatus.COMPLETED: "Đã thực hiện",
    ChecklistResultStatus.PASS: "Đạt",
    ChecklistResultStatus.FAIL: "Không đạt",
    ChecklistResultStatus.NOT_APPLICABLE: "Không áp dụng",
}

WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.PLANNED: frozenset(
        {WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.ASSIGNED: frozenset(
        {
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.ON_HOLD,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.IN_PROGRESS: frozenset(
        {WorkOrderStatus.ON_HOLD, WorkOrderStatus.COMPLETED}
    ),
    WorkOrderStatus.ON_HOLD: frozenset(
        {WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS}
    ),
    WorkOrderStatus.COMPLETED: frozenset(
        {WorkOrderStatus.VERIFIED, WorkOrderStatus.IN_PROGRESS}
    ),
    WorkOrderStatus.VERIFIED: frozenset(),
    WorkOrderStatus.CANCELLED: frozenset(),
}

TERMINAL_WORK_ORDER_STATUSES = frozenset(
    {WorkOrderStatus.VERIFIED, WorkOrderStatus.CANCELLED}
)

WORK_ORDER_ATTACHMENT_CATEGORIES = {
    "before_photo": "Ảnh trước khi thực hiện",
    "after_photo": "Ảnh sau khi thực hiện",
    "inspection_document": "Biên bản kiểm tra",
    "completion_document": "Biên bản hoàn thành",
    "safety_document": "Tài liệu an toàn",
    "other": "Khác",
}


def recurrence_summary(interval_value: int, interval_unit: str | IntervalUnit) -> str:
    """Return a concise Vietnamese description for a controlled interval."""

    unit = IntervalUnit(interval_unit)
    return f"Mỗi {interval_value} {INTERVAL_UNIT_LABELS[unit]}"
