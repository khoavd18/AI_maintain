"""Characterization coverage for deterministic response-language validation."""

from __future__ import annotations

import json
import unicodedata

import pytest

from src.llm.base import LLMOutputError
from src.llm.output_parser import parse_grounded_answer


@pytest.mark.parametrize(
    "text",
    [
        "Kiểm tra thiết bị và ghi nhận tình trạng trước khi bảo trì.",
        "Kiem tra nguon dien va ghi nhan ket qua truoc khi thao lap.",
        "Tháo cụm bơm CR5 theo thứ tự trong tài liệu rồi ghi nhận từng bộ phận.",
        (
            "1. Đo điện áp dưới 50 VDC; 2. xác nhận nguồn đã ngắt; "
            "3. ghi kết quả cho RZAG71-140N theo nguồn S1."
        ),
        "Đo điện áp nguồn trước khi mở hộp.",
        # Sanitized Pump 005 structure: long, highly accented Vietnamese without any
        # dependency on the old six exact maintenance phrases.
        (
            "Tài liệu mô tả thứ tự tháo cụm chính của CR5 Model A. "
            "Tháo lần lượt đai giữ, cụm ngoài và phần quay theo trình tự đã nêu; "
            "ghi lại vị trí từng chi tiết để đối chiếu khi lắp lại."
        ),
        # Sanitized HVAC 010 structure: multiple grounded fields, technical nouns,
        # and no exact legacy marker phrase.
        (
            "Đặt công tắc về vị trí ngắt, chờ quạt dừng hẳn rồi đối chiếu mã E7. "
            "Xác nhận đầu nối X106A chắc chắn trước khi cho RZAG chạy lại."
        ),
    ],
)
def test_legitimate_vietnamese_maintenance_variants_are_accepted(text: str) -> None:
    answer = parse_grounded_answer(_answer_json(text), expected_language="vi")

    assert answer.summary == text


@pytest.mark.parametrize(
    "text",
    [
        "Inspect the equipment and record the condition before restarting the motor.",
        "asdf qwer zxcv plmokn jhgfds",
        "S1 S2 S3",
        "CR5 RZAG71-140N 50 VDC 60 Hz 31 Nm",
        "Reset controller relay terminal and reconnect motor circuit per source fragment.",
        (
            "The technician must inspect every terminal, reset the controller, and restart "
            "the equipment after documenting the result. Vui lòng kiểm tra."
        ),
        "kiem tra",
    ],
)
def test_non_vietnamese_or_token_only_content_remains_rejected(text: str) -> None:
    with pytest.raises(LLMOutputError, match="tiếng Việt"):
        parse_grounded_answer(_answer_json(text), expected_language="vi")


def test_json_keys_without_an_answer_remain_schema_invalid() -> None:
    with pytest.raises(LLMOutputError, match="schema"):
        parse_grounded_answer(
            json.dumps(
                {
                    "summary": "",
                    "summary_source_ids": ["S1"],
                    "recommended_checks": [],
                }
            ),
            expected_language="vi",
        )


def test_technical_english_nouns_are_allowed_inside_substantive_vietnamese() -> None:
    text = (
        "Xác nhận relay, controller và terminal đúng vị trí; sau đó ghi nhận trạng thái "
        "motor trước khi reset hệ thống."
    )

    assert parse_grounded_answer(_answer_json(text), expected_language="vi").summary == text


def test_decomposed_vietnamese_unicode_is_normalized_before_detection() -> None:
    text = unicodedata.normalize(
        "NFD",
        "Kiểm tra nguồn điện và ghi nhận kết quả trước khi mở hộp.",
    )

    assert parse_grounded_answer(_answer_json(text), expected_language="vi").summary == text


def test_expected_english_response_is_not_forced_through_vietnamese_detection() -> None:
    text = "Inspect the power terminal and record the measured voltage before restart."

    assert parse_grounded_answer(_answer_json(text), expected_language="en").summary == text
    with pytest.raises(LLMOutputError, match="tiếng Việt"):
        parse_grounded_answer(_answer_json(text), expected_language="vi")


def test_explicit_mixed_language_requires_substantive_content_in_both_languages() -> None:
    mixed = (
        "Kiểm tra nguồn điện và ghi nhận điện áp, then inspect the terminal and record "
        "the result before restart."
    )

    assert parse_grounded_answer(_answer_json(mixed), expected_language="mixed").summary == mixed
    with pytest.raises(LLMOutputError):
        parse_grounded_answer(
            _answer_json("Inspect the terminal and record the result before restart."),
            expected_language="mixed",
        )
    with pytest.raises(LLMOutputError):
        parse_grounded_answer(
            _answer_json("Kiểm tra nguồn điện và ghi nhận kết quả trước khi khởi động."),
            expected_language="mixed",
        )


def _answer_json(text: str) -> str:
    return json.dumps(
        {
            "summary": text,
            "summary_source_ids": ["S1"],
            "possible_causes": [],
            "recommended_checks": [{"text": text, "source_ids": ["S1"]}],
            "safety_warnings": [],
            "escalation_required": False,
            "source_ids": ["S1"],
            "confidence": "medium",
            "insufficient_evidence": False,
        },
        ensure_ascii=False,
    )
