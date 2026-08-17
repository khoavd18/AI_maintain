"""Question, rubric, and classification text helpers for Phase 2 v2."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from evaluation.phase2_v2.catalog import EvidenceSeed
from evaluation.phase2_v2.dataset_spec import Family


def _question(
    family: Family,
    category: str,
    primary: dict[str, Any],
    secondary: dict[str, Any],
    index: int,
    language_variant: str,
) -> str:
    model = {
        "PUMP": "bơm Grundfos CR 5 Model A",
        "HVAC": "Daikin RZAG71-140N",
        "GEN": "Generac MLG15 SN 3004595385+",
    }[family.code]
    title = str(primary["title_vi"]).casefold()
    second = str(secondary["title_vi"]).casefold()
    if family.code == "HVAC":
        title = title.replace("pump-down", "thu hồi môi chất")
        second = second.replace("pump-down", "thu hồi môi chất")
    context = _context(index)
    if category == "insufficient_evidence_no_answer":
        vi = _no_answer_question(family.code, model, index, context)
    elif category == "model_version_applicability_isolation":
        vi = (
            f"Có thể áp dụng hướng dẫn {title} của {model} nguyên xi cho "
            f"{_wrong_model(family.code, index)} không?"
        )
    elif category == "multi_turn_follow_up":
        vi = f"Với {model}, sau bước {title}, phần {second} cần được làm rõ thế nào?"
    elif category == "safety_escalation":
        vi = f"{context}, trước khi xử lý {title} trên {model}, điều kiện dừng và chuyển kỹ thuật viên là gì?"
    elif category == "preventive_maintenance_inspection":
        vi = f"Checklist tại {context} cho {model} cần kiểm tra {title} ra sao và ghi nhận giới hạn nào?"
    elif category == "operation_repair_procedure":
        vi = f"Trình tự an toàn để thực hiện {title} trên {model} tại {context} là gì?"
    elif category == "language_typo_abbreviation_robustness":
        vi = f"{model}: kt {title} luc ca dem, can lam gi truoc?"
    else:
        vi = f"{context}, {model} có dấu hiệu liên quan đến {title}; nên kiểm tra nguyên nhân và giới hạn xử lý nào trước?"
    if language_variant == "vi_no_diacritics":
        return _strip_accents(vi).replace("khong", "ko", 1).replace("kiem tra", "kt", 1)
    if language_variant == "en" and category == "insufficient_evidence_no_answer":
        return _strip_accents(vi)
    if language_variant == "en" and category == "model_version_applicability_isolation":
        return (
            f"Can the {model} procedure be applied unchanged to {_wrong_model(family.code, index)}?"
        )
    if language_variant == "en":
        return f"For {model}, during {_context_en(index)}, what evidence-backed check applies to {primary['title_en']}?"
    if language_variant == "mixed_vi_en" and category == "insufficient_evidence_no_answer":
        return {
            "PUMP": f"{model}: cần exact Nm nhưng chưa biết screw size thì trả lời sao?",
            "HVAC": f"{model}: cần exact refrigerant charge nhưng thiếu pipe size/length thì sao?",
            "GEN": f"{model}: cần exact SAE oil nhưng thiếu engine manual/ambient temperature thì sao?",
        }[family.code]
    if language_variant == "mixed_vi_en" and category == "model_version_applicability_isolation":
        return (
            f"Procedure của {model} có apply nguyên xi cho "
            f"{_wrong_model(family.code, index)} không?"
        )
    if language_variant == "mixed_vi_en":
        return f"{context}, {model} báo issue về {primary['title_en']}; cần safety check và escalation nào?"
    return vi


def _context(index: int) -> str:
    contexts = (
        "trước ca sáng",
        "sau thời gian dừng dài",
        "khi kiểm tra định kỳ",
        "sau cảnh báo lặp lại",
        "trước khi tháo panel",
        "khi bàn giao giữa ca",
        "sau khi thay chi tiết",
        "trước test run",
        "khi thiết bị còn nóng",
        "sau khi phát hiện rò",
        "trước khi cấp lại nguồn",
        "khi lập phiếu kiểm tra",
    )
    return contexts[(index - 1) % len(contexts)]


def _context_en(index: int) -> str:
    values = (
        "pre-shift inspection",
        "restart after a long stop",
        "scheduled inspection",
        "repeated alarm diagnosis",
        "panel access preparation",
        "shift handover",
        "post-repair verification",
        "test-run preparation",
        "hot-equipment cooldown",
        "leak assessment",
        "controlled re-energization",
        "maintenance record review",
    )
    return values[(index - 1) % len(values)]


def _no_answer_question(family_code: str, model: str, index: int, context: str) -> str:
    slot = index % 10
    if family_code == "PUMP":
        targets = (
            "vít khớp nối khi chưa biết cỡ vít",
            "vít động cơ khi chưa xác định cỡ ren",
            "ty giằng khi chưa biết biến thể CR, CRI hay CRN",
            "vít phớt khi chưa nhận diện đúng vị trí 113",
            "đai ốc khóa khi chưa xác định vị trí 67",
            "nút xả khi chưa xác định spindle",
            "vít bích khi chưa biết loại bích",
            "phớt trục khi chưa xác định mã seal",
            "vòng bi khi chưa xác định stage variant",
            "khớp nối khi nameplate không đọc được",
        )
        return f"{context}, khi bảo trì {model}, {targets[slot]} phải siết chính xác bao nhiêu Nm?"
    if family_code == "HVAC":
        targets = (
            "không có cỡ ống và chiều dài",
            "chưa xác định model 71, 100, 125 hay 140",
            "chưa biết bố trí pair, twin hay triple",
            "thiếu tổng chiều dài một chiều",
            "thiếu cỡ liquid pipe",
            "chưa xác định lượng nạp nhà máy",
            "không có chênh cao đường ống",
            "thiếu cấu hình size-down hay standard",
            "không có dữ liệu nhãn F-gas",
            "chưa hoàn tất kiểm tra rò",
        )
        return f"{context}, {model} phải nạp chính xác bao nhiêu refrigerant khi {targets[slot]}?"
    targets = (
        "thiếu manual động cơ và nhiệt độ môi trường",
        "chưa xác định engine MVS4L2-W464ML",
        "không có cấp dầu trong engine manual",
        "chưa biết điều kiện tải và môi trường",
        "không có coolant recommendation của engine OEM",
        "thiếu service record về oil grade",
        "chưa xác nhận serial trên unit ID tag",
        "không có hướng dẫn emissions của engine OEM",
        "chưa xác định nhiệt độ thấp nhất tại nơi vận hành",
        "chưa có xác nhận từ đại lý được ủy quyền",
    )
    return f"{context}, {model} phải dùng chính xác dầu SAE nào khi {targets[slot]}?"


def _wrong_model(family_code: str, index: int) -> str:
    values = {
        "PUMP": (
            "CR 10",
            "CR 15",
            "CR 20",
            "CR 32",
            "CR 45",
            "CR 64",
            "CR 90",
            "CR 120",
            "CR 150",
            "CR 155",
        ),
        "HVAC": (
            "RZAG50N",
            "RZAG60N",
            "RZAG160N",
            "RZAG180N",
            "RZAG200N",
            "RZAG40N",
            "RZAG55N",
            "RZAG65N",
            "RZAG150N",
            "RZAG170N",
        ),
        "GEN": (
            "MLG8",
            "MLG20",
            "MLG25",
            "MLG30",
            "MLG45",
            "MLG60",
            "MLG75",
            "MLG90",
            "MLG100",
            "MLG150",
        ),
    }
    return values[family_code][index % 10]


def _response_policy(category: str) -> str:
    if category == "insufficient_evidence_no_answer":
        return "refuse_insufficient_evidence"
    if category == "model_version_applicability_isolation":
        return "escalate_manual_review"
    return "answer_with_evidence"


def _case_type(category: str) -> str:
    return {
        "troubleshooting": "troubleshooting",
        "operation_repair_procedure": "operation",
        "preventive_maintenance_inspection": "maintenance",
        "safety_escalation": "safety",
        "insufficient_evidence_no_answer": "evidence_boundary",
        "model_version_applicability_isolation": "model_isolation",
        "multi_turn_follow_up": "multi_turn",
        "language_typo_abbreviation_robustness": "robustness",
    }[category]


def _intent(category: str) -> str:
    if category == "troubleshooting":
        return "troubleshooting"
    if category == "preventive_maintenance_inspection":
        return "preventive"
    if category == "safety_escalation":
        return "safety"
    return "factual"


def _expected_behavior(category: str) -> str:
    if category == "insufficient_evidence_no_answer":
        return "clarify_before_answer"
    if category == "model_version_applicability_isolation":
        return "refuse_model_mismatch_and_request_source"
    return "grounded_answer_with_safety_gate"


def _question_form(category: str, language: str) -> str:
    if category == "insufficient_evidence_no_answer":
        return "forced_specificity_missing_source"
    if category == "model_version_applicability_isolation":
        return "wrong_model_variant"
    if language in {"vi_no_diacritics", "mixed_vi_en"}:
        return "technician_robustness"
    return "natural_language"


def _language_code(variant: str) -> str:
    return {"vi_diacritics": "vi", "vi_no_diacritics": "vi", "en": "en", "mixed_vi_en": "vi-en"}[
        variant
    ]


def _document_type(item: EvidenceSeed) -> str:
    section = item.section.casefold()
    if "maintenance" in section or "check" in section:
        return "Danh sách kiểm tra"
    if "troubleshoot" in section or item.safety_tags:
        return "Hướng dẫn xử lý sự cố"
    return "Quy trình vận hành chuẩn"


def _failure_category(item: EvidenceSeed) -> str:
    tags = set(item.safety_tags)
    if tags & {"electrical", "electrocution", "electrical_isolation"}:
        return "Lỗi điện"
    if tags & {"vibration", "rotating_parts", "alignment"}:
        return "Lỗi rung động"
    if tags & {"pressure", "pressure_system"}:
        return "Lỗi áp suất"
    return ""


def _normalize_question(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold())
    unaccented = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", unaccented).strip()


def _strip_accents(value: str) -> str:
    folded = unicodedata.normalize("NFD", value)
    return (
        "".join(char for char in folded if unicodedata.category(char) != "Mn")
        .replace("đ", "d")
        .replace("Đ", "D")
    )
