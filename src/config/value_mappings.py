"""Vietnamese business labels and internal-code mappings.

Column names and Python identifiers stay in English for engineering consistency.
Generated business values are Vietnamese for facility managers and technicians.
"""

from collections.abc import Mapping

ASSET_TYPE_CODE_TO_VI = {
    "hvac": "Máy lạnh",
    "pump": "Máy bơm nước",
    "elevator": "Thang máy",
    "generator": "Máy phát điện dự phòng",
    "lighting": "Hệ thống chiếu sáng",
    "electrical_panel": "Tủ điện",
    "water_tank": "Bồn nước",
    "fire_safety": "Hệ thống báo cháy",
}
ASSET_TYPE_VI_TO_CODE = {value: key for key, value in ASSET_TYPE_CODE_TO_VI.items()}

PRIORITY_CODE_TO_VI = {
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "critical": "Khẩn cấp",
}
PRIORITY_VI_TO_SCORE = {
    "Thấp": 1,
    "Trung bình": 2,
    "Cao": 3,
    "Khẩn cấp": 4,
}
PRIORITY_VI_TO_CODE = {value: key for key, value in PRIORITY_CODE_TO_VI.items()}

STATUS_CODE_TO_VI = {
    "open": "Mới tạo",
    "in_progress": "Đang xử lý",
    "resolved": "Đã xử lý",
    "closed": "Đã đóng",
    "normal": "Bình thường",
    "warning": "Cảnh báo",
    "fault": "Sự cố",
}
STATUS_VI_TO_CODE = {value: key for key, value in STATUS_CODE_TO_VI.items()}

CRITICALITY_CODE_TO_VI = {
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "critical": "Rất quan trọng",
}
CRITICALITY_VI_TO_SCORE = {
    "Thấp": 1,
    "Trung bình": 2,
    "Cao": 3,
    "Rất quan trọng": 4,
}
CRITICALITY_VI_TO_CODE = {value: key for key, value in CRITICALITY_CODE_TO_VI.items()}

MAINTENANCE_TYPE_CODE_TO_VI = {
    "preventive": "Bảo trì định kỳ",
    "corrective": "Bảo trì sửa chữa",
    "inspection": "Kiểm tra",
    "emergency": "Xử lý khẩn cấp",
}
MAINTENANCE_TYPE_VI_TO_CODE = {
    value: key for key, value in MAINTENANCE_TYPE_CODE_TO_VI.items()
}

DOCUMENT_TYPE_CODE_TO_VI = {
    "sop": "Quy trình vận hành chuẩn",
    "checklist": "Danh sách kiểm tra",
    "troubleshooting_guide": "Hướng dẫn xử lý sự cố",
}
DOCUMENT_TYPE_VI_TO_CODE = {value: key for key, value in DOCUMENT_TYPE_CODE_TO_VI.items()}

FAILURE_TYPE_CODE_TO_VI = {
    "cooling_issue": "Lỗi làm lạnh",
    "vibration_issue": "Lỗi rung động",
    "electrical_issue": "Lỗi điện",
    "pressure_issue": "Lỗi áp suất",
    "runtime_issue": "Lỗi thời gian vận hành",
    "sensor_issue": "Lỗi cảm biến",
    "false_alarm": "Cảnh báo giả",
    "no_failure": "Không có lỗi",
}
FAILURE_TYPE_VI_TO_CODE = {value: key for key, value in FAILURE_TYPE_CODE_TO_VI.items()}

ANOMALY_TYPE_CODE_TO_VI = {
    "none": "Không bất thường",
    "energy_spike": "Tăng điện năng bất thường",
    "vibration_increase": "Độ rung tăng bất thường",
    "runtime_abnormal": "Thời gian vận hành bất thường",
    "temperature_high": "Nhiệt độ cao bất thường",
    "pressure_drop": "Giảm áp suất bất thường",
    "electrical_overheat": "Tủ điện quá nhiệt",
}
ANOMALY_TYPE_VI_TO_CODE = {value: key for key, value in ANOMALY_TYPE_CODE_TO_VI.items()}

RISK_LEVEL_CODE_TO_VI = {
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "critical": "Khẩn cấp",
}
RISK_LEVEL_VI_TO_CODE = {value: key for key, value in RISK_LEVEL_CODE_TO_VI.items()}


def to_internal_code(value: str, mapping: Mapping[str, str], field_name: str) -> str:
    """Convert a Vietnamese business value into a stable internal code."""

    try:
        return mapping[value]
    except KeyError as exc:
        raise ValueError(f"Unknown {field_name} value: {value}") from exc


def priority_score(priority: str) -> int:
    """Return a numeric priority score from a Vietnamese priority label."""

    try:
        return PRIORITY_VI_TO_SCORE[priority]
    except KeyError as exc:
        raise ValueError(f"Unknown priority value: {priority}") from exc


def criticality_score(criticality: str) -> int:
    """Return a numeric criticality score from a Vietnamese criticality label."""

    try:
        return CRITICALITY_VI_TO_SCORE[criticality]
    except KeyError as exc:
        raise ValueError(f"Unknown criticality value: {criticality}") from exc
