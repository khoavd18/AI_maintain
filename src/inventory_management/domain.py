"""Canonical inventory codes, Vietnamese labels, and derived quantities."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class PartLifecycleStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class StockLocationType(StrEnum):
    MAIN_STORE = "main_store"
    ENGINEERING_STORE = "engineering_store"
    TECHNICIAN_VAN = "technician_van"
    MAINTENANCE_ROOM = "maintenance_room"
    QUARANTINE = "quarantine"
    OTHER = "other"


class StockLocationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class InventoryMovementType(StrEnum):
    OPENING_BALANCE = "opening_balance"
    RECEIPT = "receipt"
    ISSUE = "issue"
    RETURN = "return"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    ADJUSTMENT_INCREASE = "adjustment_increase"
    ADJUSTMENT_DECREASE = "adjustment_decrease"
    DAMAGED_SCRAPPED = "damaged_scrapped"


class InventoryOperationType(StrEnum):
    OPENING_BALANCE = "opening_balance"
    RECEIPT = "receipt"
    RESERVE = "reserve"
    RELEASE_RESERVATION = "release_reservation"
    EXPIRE_RESERVATION = "expire_reservation"
    REPLACE_RESERVATION = "replace_reservation"
    ISSUE = "issue"
    CONSUME = "consume"
    RETURN = "return"
    TRANSFER = "transfer"
    ADJUSTMENT_INCREASE = "adjustment_increase"
    ADJUSTMENT_DECREASE = "adjustment_decrease"
    DAMAGED_SCRAPPED = "damaged_scrapped"


class RequirementStatus(StrEnum):
    PLANNED = "planned"
    PARTIALLY_RESERVED = "partially_reserved"
    RESERVED = "reserved"
    PARTIALLY_ISSUED = "partially_issued"
    ISSUED = "issued"
    PARTIALLY_CONSUMED = "partially_consumed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    PARTIALLY_ISSUED = "partially_issued"
    FULFILLED = "fulfilled"
    RELEASED = "released"
    EXPIRED = "expired"
    REPLACED = "replaced"


class StockState(StrEnum):
    HEALTHY = "healthy"
    LOW_STOCK = "low_stock"
    AT_REORDER_POINT = "at_reorder_point"
    OUT_OF_STOCK = "out_of_stock"
    OVERSTOCK = "overstock"


PART_LIFECYCLE_LABELS = {
    PartLifecycleStatus.ACTIVE: "Đang hoạt động",
    PartLifecycleStatus.INACTIVE: "Ngừng hoạt động",
    PartLifecycleStatus.ARCHIVED: "Đã lưu trữ",
}
STOCK_LOCATION_TYPE_LABELS = {
    StockLocationType.MAIN_STORE: "Kho chính",
    StockLocationType.ENGINEERING_STORE: "Kho kỹ thuật",
    StockLocationType.TECHNICIAN_VAN: "Kho xe kỹ thuật",
    StockLocationType.MAINTENANCE_ROOM: "Phòng bảo trì",
    StockLocationType.QUARANTINE: "Khu cách ly hoặc hư hỏng",
    StockLocationType.OTHER: "Khác",
}
STOCK_LOCATION_STATUS_LABELS = {
    StockLocationStatus.ACTIVE: "Đang hoạt động",
    StockLocationStatus.INACTIVE: "Ngừng hoạt động",
    StockLocationStatus.ARCHIVED: "Đã lưu trữ",
}
MOVEMENT_TYPE_LABELS = {
    InventoryMovementType.OPENING_BALANCE: "Số dư đầu kỳ",
    InventoryMovementType.RECEIPT: "Nhập kho",
    InventoryMovementType.ISSUE: "Xuất cho công việc",
    InventoryMovementType.RETURN: "Hoàn trả",
    InventoryMovementType.TRANSFER_OUT: "Chuyển kho đi",
    InventoryMovementType.TRANSFER_IN: "Chuyển kho đến",
    InventoryMovementType.ADJUSTMENT_INCREASE: "Điều chỉnh tăng",
    InventoryMovementType.ADJUSTMENT_DECREASE: "Điều chỉnh giảm",
    InventoryMovementType.DAMAGED_SCRAPPED: "Hư hỏng hoặc loại bỏ",
}
REQUIREMENT_STATUS_LABELS = {
    RequirementStatus.PLANNED: "Đã lập kế hoạch",
    RequirementStatus.PARTIALLY_RESERVED: "Giữ một phần",
    RequirementStatus.RESERVED: "Đã giữ đủ",
    RequirementStatus.PARTIALLY_ISSUED: "Đã xuất một phần",
    RequirementStatus.ISSUED: "Đã xuất đủ",
    RequirementStatus.PARTIALLY_CONSUMED: "Đã dùng một phần",
    RequirementStatus.FULFILLED: "Đã sử dụng đủ",
    RequirementStatus.CANCELLED: "Đã hủy",
}
RESERVATION_STATUS_LABELS = {
    ReservationStatus.ACTIVE: "Đang giữ",
    ReservationStatus.PARTIALLY_ISSUED: "Đã xuất một phần",
    ReservationStatus.FULFILLED: "Đã xuất hết",
    ReservationStatus.RELEASED: "Đã giải phóng",
    ReservationStatus.EXPIRED: "Đã hết hạn thủ công",
    ReservationStatus.REPLACED: "Đã thay thế",
}
STOCK_STATE_LABELS = {
    StockState.HEALTHY: "Đủ tồn kho",
    StockState.LOW_STOCK: "Tồn kho thấp",
    StockState.AT_REORDER_POINT: "Đến điểm đặt lại",
    StockState.OUT_OF_STOCK: "Hết hàng",
    StockState.OVERSTOCK: "Vượt mức tối đa",
}

ACTIVE_RESERVATION_STATUSES = frozenset(
    {ReservationStatus.ACTIVE, ReservationStatus.PARTIALLY_ISSUED}
)
ISSUABLE_WORK_ORDER_STATUSES = frozenset({"assigned", "in_progress", "on_hold"})
REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES = frozenset(
    {"planned", "assigned", "in_progress", "on_hold"}
)
INVENTORY_ATTACHMENT_CATEGORIES = {
    "adjustment_evidence": "Bằng chứng điều chỉnh",
    "damage_evidence": "Bằng chứng hư hỏng",
    "receipt_evidence": "Bằng chứng nhập kho",
    "transfer_evidence": "Bằng chứng chuyển kho",
    "other": "Khác",
}


def available_quantity(on_hand: Decimal, reserved: Decimal) -> Decimal:
    """Return the canonical available quantity without accepting a client value."""

    return on_hand - reserved


def derive_stock_state(
    *,
    on_hand: Decimal,
    reserved: Decimal,
    minimum_stock: Decimal,
    reorder_point: Decimal,
    maximum_stock: Decimal | None,
) -> StockState:
    """Derive one deterministic stock state from server-side quantities."""

    available = available_quantity(on_hand, reserved)
    if available <= 0:
        return StockState.OUT_OF_STOCK
    if available < minimum_stock:
        return StockState.LOW_STOCK
    if available <= reorder_point:
        return StockState.AT_REORDER_POINT
    if maximum_stock is not None and on_hand > maximum_stock:
        return StockState.OVERSTOCK
    return StockState.HEALTHY


def reorder_suggestion(
    *,
    available: Decimal,
    reorder_point: Decimal,
    maximum_stock: Decimal | None,
) -> Decimal:
    """Suggest a deterministic top-up only when availability reaches the threshold."""

    if available > reorder_point:
        return Decimal("0")
    target = maximum_stock if maximum_stock is not None else reorder_point
    return max(target - available, Decimal("0"))
