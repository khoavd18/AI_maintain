"""Release-record tests grouped by validation capability."""

from __future__ import annotations

from ._release_record_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_documents,
    pytest,
)


def test_operational_validation_sections_follow_fixed_order() -> None:
    *_, record = _ready_documents()
    for section_name in (
        "backup_validation",
        "restore_validation",
        "attachment_restore",
        "secret_rotation",
    ):
        record[section_name] = {"status": "failed"}

    assert _only(_findings(record=record)[1], {"release_validation_open"}) == [
        _finding(
            "release_validation_open",
            f"release_record.{section_name}",
            f"{section_name} chưa có kết quả passed cho pilot.",
        )
        for section_name in (
            "backup_validation",
            "restore_validation",
            "attachment_restore",
            "secret_rotation",
        )
    ]


@pytest.mark.parametrize(
    "section_name",
    ["backup_validation", "restore_validation", "attachment_restore", "secret_rotation"],
)
def test_passed_validation_requires_timestamp_and_evidence(section_name: str) -> None:
    *_, record = _ready_documents()
    record[section_name] = {"status": "passed", "validated_at_utc": "bad", "evidence_links": []}

    assert _only(_findings(record=record)[1], {"validation_evidence_missing"}) == [
        _finding(
            "validation_evidence_missing",
            f"release_record.{section_name}",
            f"{section_name} passed nhưng thiếu timestamp hoặc evidence.",
        )
    ]


@pytest.mark.parametrize(
    "load_profiles",
    [
        None,
        {},
        {"status": "passed", "summaries": [], "evidence_links": ["evidence/x"]},
        {"status": "passed", "summaries": [{}], "evidence_links": []},
    ],
)
def test_load_and_soak_requires_passed_summary_and_evidence(load_profiles: object) -> None:
    *_, record = _ready_documents()
    record["load_and_soak_profiles"] = load_profiles

    assert _only(_findings(record=record)[1], {"load_and_soak_evidence_open"}) == [
        _finding(
            "load_and_soak_evidence_open",
            "release_record.load_and_soak_profiles",
            "Load và soak profiles chưa có summary cùng evidence passed.",
        )
    ]
