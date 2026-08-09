"""Closed job and outbox catalogs for durable background operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.security.permissions import Role


class JobType(StrEnum):
    PREVENTIVE_GENERATION = "preventive_generation"
    SLA_ESCALATION = "sla_escalation"
    ANALYTICS_REFRESH = "analytics_refresh"
    INVENTORY_REORDER_DETECTION = "inventory_reorder_detection"


class JobExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class JobSpec:
    display_name: str
    default_interval_seconds: int
    default_lease_seconds: int
    default_max_attempts: int
    default_retry_backoff_seconds: int


JOB_CATALOG: dict[JobType, JobSpec] = {
    JobType.PREVENTIVE_GENERATION: JobSpec(
        display_name="Sinh work order bảo trì định kỳ",
        default_interval_seconds=3600,
        default_lease_seconds=300,
        default_max_attempts=3,
        default_retry_backoff_seconds=30,
    ),
    JobType.SLA_ESCALATION: JobSpec(
        display_name="Đánh giá SLA và escalation",
        default_interval_seconds=300,
        default_lease_seconds=180,
        default_max_attempts=3,
        default_retry_backoff_seconds=30,
    ),
    JobType.ANALYTICS_REFRESH: JobSpec(
        display_name="Làm mới batch analytics",
        default_interval_seconds=86400,
        default_lease_seconds=3600,
        default_max_attempts=2,
        default_retry_backoff_seconds=120,
    ),
    JobType.INVENTORY_REORDER_DETECTION: JobSpec(
        display_name="Phát hiện tồn kho dưới điểm đặt hàng",
        default_interval_seconds=900,
        default_lease_seconds=180,
        default_max_attempts=3,
        default_retry_backoff_seconds=30,
    ),
}


@dataclass(frozen=True)
class EventSpec:
    aggregate_type: str
    required_fields: frozenset[str]
    allowed_fields: frozenset[str]
    recipient_roles: frozenset[Role]
    severity: NotificationSeverity
    title: str
    body_template: str
    related_entity_type: str
    explicit_recipient_fields: tuple[str, ...] = ()


def _fields(*values: str) -> frozenset[str]:
    return frozenset(values)


EVENT_CATALOG: dict[str, EventSpec] = {
    "ticket.critical_created": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "asset_id", "priority"),
        allowed_fields=_fields("ticket_id", "asset_id", "priority"),
        recipient_roles=frozenset(
            {Role.ADMINISTRATOR, Role.PROPERTY_MANAGER, Role.CHIEF_ENGINEER}
        ),
        severity=NotificationSeverity.CRITICAL,
        title="Ticket nghiêm trọng mới",
        body_template="Ticket {ticket_id} của asset {asset_id} cần được đánh giá ưu tiên.",
        related_entity_type="ticket",
    ),
    "ticket.assigned": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "asset_id", "assigned_user_id"),
        allowed_fields=_fields("ticket_id", "asset_id", "assigned_user_id"),
        recipient_roles=frozenset(),
        severity=NotificationSeverity.INFO,
        title="Ticket được phân công",
        body_template="Ticket {ticket_id} của asset {asset_id} đã được phân công cho bạn.",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "ticket.held": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "asset_id"),
        allowed_fields=_fields("ticket_id", "asset_id", "assigned_user_id"),
        recipient_roles=frozenset({Role.CHIEF_ENGINEER}),
        severity=NotificationSeverity.WARNING,
        title="Ticket đang chờ xử lý",
        body_template="Ticket {ticket_id} của asset {asset_id} đã chuyển sang trạng thái chờ.",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "ticket.resumed": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "asset_id"),
        allowed_fields=_fields("ticket_id", "asset_id", "assigned_user_id"),
        recipient_roles=frozenset({Role.CHIEF_ENGINEER}),
        severity=NotificationSeverity.INFO,
        title="Ticket tiếp tục xử lý",
        body_template="Ticket {ticket_id} của asset {asset_id} đã được tiếp tục.",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "ticket.sla_warning": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "rule_code"),
        allowed_fields=_fields(
            "ticket_id",
            "asset_id",
            "rule_code",
            "clock_type",
            "occurrence_number",
            "assigned_user_id",
        ),
        recipient_roles=frozenset(
            {Role.ADMINISTRATOR, Role.PROPERTY_MANAGER, Role.CHIEF_ENGINEER}
        ),
        severity=NotificationSeverity.WARNING,
        title="SLA sắp đến hạn",
        body_template="Ticket {ticket_id} đang tiến gần ngưỡng SLA ({rule_code}).",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "ticket.sla_breach": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "rule_code"),
        allowed_fields=_fields(
            "ticket_id",
            "asset_id",
            "rule_code",
            "clock_type",
            "occurrence_number",
            "assigned_user_id",
        ),
        recipient_roles=frozenset(
            {Role.ADMINISTRATOR, Role.PROPERTY_MANAGER, Role.CHIEF_ENGINEER}
        ),
        severity=NotificationSeverity.CRITICAL,
        title="SLA đã vượt ngưỡng",
        body_template="Ticket {ticket_id} đã vượt ngưỡng SLA ({rule_code}).",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "ticket.escalated": EventSpec(
        aggregate_type="ticket",
        required_fields=_fields("ticket_id", "rule_code"),
        allowed_fields=_fields(
            "ticket_id",
            "asset_id",
            "rule_code",
            "clock_type",
            "occurrence_number",
            "assigned_user_id",
        ),
        recipient_roles=frozenset(
            {Role.ADMINISTRATOR, Role.PROPERTY_MANAGER, Role.CHIEF_ENGINEER}
        ),
        severity=NotificationSeverity.WARNING,
        title="Ticket được escalation",
        body_template="Ticket {ticket_id} có escalation mới ({rule_code}).",
        related_entity_type="ticket",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "work_order.assigned": EventSpec(
        aggregate_type="work_order",
        required_fields=_fields(
            "work_order_id", "work_order_number", "asset_id", "assigned_user_id"
        ),
        allowed_fields=_fields(
            "work_order_id", "work_order_number", "asset_id", "assigned_user_id"
        ),
        recipient_roles=frozenset(),
        severity=NotificationSeverity.INFO,
        title="Work order được phân công",
        body_template=(
            "Work order {work_order_number} của asset {asset_id} đã được phân công cho bạn."
        ),
        related_entity_type="work_order",
        explicit_recipient_fields=("assigned_user_id",),
    ),
    "work_order.completed": EventSpec(
        aggregate_type="work_order",
        required_fields=_fields("work_order_id", "work_order_number", "asset_id"),
        allowed_fields=_fields(
            "work_order_id",
            "work_order_number",
            "asset_id",
            "assigned_user_id",
        ),
        recipient_roles=frozenset({Role.PROPERTY_MANAGER, Role.CHIEF_ENGINEER}),
        severity=NotificationSeverity.INFO,
        title="Work order chờ xác minh",
        body_template=(
            "Work order {work_order_number} của asset {asset_id} đã hoàn thành và chờ xác minh."
        ),
        related_entity_type="work_order",
    ),
    "inventory.issue_completed": EventSpec(
        aggregate_type="inventory_issue",
        required_fields=_fields("issue_id", "issue_number", "work_order_id"),
        allowed_fields=_fields(
            "issue_id",
            "issue_number",
            "work_order_id",
            "part_id",
            "stock_location_id",
            "issued_to_user_id",
        ),
        recipient_roles=frozenset({Role.STOREKEEPER}),
        severity=NotificationSeverity.INFO,
        title="Đã xuất vật tư",
        body_template="Phiếu xuất {issue_number} cho work order {work_order_id} đã hoàn tất.",
        related_entity_type="inventory_issue",
        explicit_recipient_fields=("issued_to_user_id",),
    ),
    "preventive.work_orders_generated": EventSpec(
        aggregate_type="maintenance_generation",
        required_fields=_fields("plan_id", "plan_code", "generated_count"),
        allowed_fields=_fields(
            "plan_id", "plan_code", "generated_count", "skipped_count"
        ),
        recipient_roles=frozenset({Role.CHIEF_ENGINEER}),
        severity=NotificationSeverity.INFO,
        title="Đã sinh work order định kỳ",
        body_template=(
            "Kế hoạch {plan_code} đã sinh {generated_count} work order; "
            "{skipped_count} occurrence được bỏ qua."
        ),
        related_entity_type="maintenance_plan",
    ),
    "inventory.stock_below_reorder": EventSpec(
        aggregate_type="inventory_position",
        required_fields=_fields(
            "part_id",
            "part_number",
            "stock_location_id",
            "stock_location_code",
            "available_quantity",
            "reorder_point",
            "cycle_number",
        ),
        allowed_fields=_fields(
            "part_id",
            "part_number",
            "stock_location_id",
            "stock_location_code",
            "available_quantity",
            "reorder_point",
            "stock_state",
            "cycle_number",
        ),
        recipient_roles=frozenset(
            {Role.ADMINISTRATOR, Role.CHIEF_ENGINEER, Role.STOREKEEPER}
        ),
        severity=NotificationSeverity.WARNING,
        title="Tồn kho dưới điểm đặt hàng",
        body_template=(
            "Vật tư {part_number} tại {stock_location_code} còn "
            "{available_quantity}, dưới ngưỡng {reorder_point}."
        ),
        related_entity_type="part",
    ),
    "analytics.refresh_failed": EventSpec(
        aggregate_type="job_execution",
        required_fields=_fields("execution_id", "error_code"),
        allowed_fields=_fields("execution_id", "error_code"),
        recipient_roles=frozenset({Role.ADMINISTRATOR, Role.PROPERTY_MANAGER}),
        severity=NotificationSeverity.CRITICAL,
        title="Batch analytics thất bại",
        body_template=(
            "Lần làm mới analytics {execution_id} thất bại ({error_code}). "
            "Kết quả hợp lệ gần nhất vẫn được giữ nguyên."
        ),
        related_entity_type="job_execution",
    ),
    "operations.alert_raised": EventSpec(
        aggregate_type="operational_alert",
        required_fields=_fields(
            "alert_type",
            "alert_name",
            "entity_key",
            "cycle_number",
            "observed_value",
            "threshold_value",
        ),
        allowed_fields=_fields(
            "alert_type",
            "alert_name",
            "entity_key",
            "cycle_number",
            "observed_value",
            "threshold_value",
        ),
        recipient_roles=frozenset({Role.ADMINISTRATOR}),
        severity=NotificationSeverity.CRITICAL,
        title="Cảnh báo độ tin cậy nội bộ",
        body_template=(
            "{alert_name}: giá trị quan sát {observed_value}, "
            "ngưỡng {threshold_value}. Cần kiểm tra runbook."
        ),
        related_entity_type="operational_alert",
    ),
    "operations.alert_recovered": EventSpec(
        aggregate_type="operational_alert",
        required_fields=_fields(
            "alert_type",
            "alert_name",
            "entity_key",
            "cycle_number",
            "observed_value",
            "threshold_value",
        ),
        allowed_fields=_fields(
            "alert_type",
            "alert_name",
            "entity_key",
            "cycle_number",
            "observed_value",
            "threshold_value",
        ),
        recipient_roles=frozenset({Role.ADMINISTRATOR}),
        severity=NotificationSeverity.INFO,
        title="Điều kiện độ tin cậy đã phục hồi",
        body_template=(
            "{alert_name} đã trở lại trong ngưỡng: "
            "{observed_value}/{threshold_value}."
        ),
        related_entity_type="operational_alert",
    ),
}


FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "storage_key",
        "file_body",
        "reporter_email",
        "reporter_phone",
    }
)

MIN_JOB_INTERVAL_SECONDS = 30
MAX_JOB_INTERVAL_SECONDS = 604800
MAX_SAFE_ERROR_LENGTH = 1000
MAX_OUTBOX_ATTEMPTS = 5
OUTBOX_RETRY_BACKOFF_SECONDS = 30


def validate_job_configuration(
    job_type: str,
    *,
    interval_seconds: int,
    timezone_name: str,
    configuration_payload: dict[str, Any],
) -> JobType:
    """Reject unsupported jobs and executable or unbounded configuration."""

    normalized = JobType(job_type)
    if not MIN_JOB_INTERVAL_SECONDS <= interval_seconds <= MAX_JOB_INTERVAL_SECONDS:
        raise ValueError(
            f"interval_seconds phải nằm trong {MIN_JOB_INTERVAL_SECONDS}–"
            f"{MAX_JOB_INTERVAL_SECONDS}."
        )
    if timezone_name != "Asia/Ho_Chi_Minh":
        raise ValueError("PM7 chỉ hỗ trợ timezone Asia/Ho_Chi_Minh.")
    if configuration_payload:
        raise ValueError(
            "Job PM7 không nhận cấu hình tùy ý; hành vi được kiểm soát phía server."
        )
    return normalized


def safe_error(exc: BaseException) -> tuple[str, str]:
    """Return a bounded public error without paths, payloads, or stack traces."""

    code = type(exc).__name__[:80] or "operation_error"
    safe_messages = {
        "FileNotFoundError": "Thiếu dữ liệu đầu vào bắt buộc.",
        "PermissionError": "Không thể truy cập thư mục runtime đã cấu hình.",
        "TimeoutError": "Thao tác vượt quá thời gian cho phép.",
        "OperationalError": "PostgreSQL tạm thời không khả dụng.",
        "StorageUnavailableError": "Kho dữ liệu tạm thời không khả dụng.",
    }
    summary = safe_messages.get(code, "Tác vụ nền không thể hoàn tất an toàn.")
    return code, summary[:MAX_SAFE_ERROR_LENGTH]
