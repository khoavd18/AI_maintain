"""Release-record tests grouped by validation capability."""

from __future__ import annotations

from ._release_record_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_documents,
)


def test_risk_id_duplicate_and_field_findings_keep_row_order() -> None:
    *_, record = _ready_documents()
    record["open_risks"] = [
        {"id": "R1", "status": "closed", "severity": "unknown", "category": "unknown"},
        {"id": "R1", "status": "open", "severity": "low", "category": "usability"},
        {"id": "TBD", "status": None, "severity": None, "category": None},
    ]

    assert [
        finding.code
        for finding in _only(
            _findings(record=record)[1],
            {
                "risk_id_missing",
                "duplicate_risk",
                "risk_status_invalid",
                "risk_severity_invalid",
                "risk_category_invalid",
            },
        )
    ] == [
        "risk_status_invalid",
        "risk_severity_invalid",
        "risk_category_invalid",
        "duplicate_risk",
        "risk_id_missing",
        "risk_status_invalid",
        "risk_severity_invalid",
        "risk_category_invalid",
    ]


def test_empty_open_risk_register_is_valid_for_this_validator() -> None:
    *_, record = _ready_documents()
    record["open_risks"] = []

    assert not {
        "risk_id_missing",
        "duplicate_risk",
        "risk_status_invalid",
        "risk_severity_invalid",
        "risk_category_invalid",
    } & {finding.code for finding in _findings(record=record)[1]}


def test_release_evidence_and_governance_summaries_keep_order() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["evidence_links"] = []
    record["known_limitations_acceptance_status"] = "pending"
    record["incident_contact_status"] = "wrong"
    record["ownership_status"] = {}

    assert _only(
        _findings(
            record=record,
            manifest=manifest,
            ownership=ownership,
            limitations=limitations,
        )[1],
        {
            "release_evidence_links_missing",
            "limitation_summary_mismatch",
            "incident_summary_mismatch",
            "ownership_summary_mismatch",
        },
    ) == [
        _finding(
            "release_evidence_links_missing",
            "release_record.evidence_links",
            "Release record phải có ít nhất một evidence-document link.",
        ),
        _finding(
            "limitation_summary_mismatch",
            "release_record.known_limitations_acceptance_status",
            "Known-limitations summary không khớp acceptance record.",
        ),
        _finding(
            "incident_summary_mismatch",
            "release_record.incident_contact_status",
            "Incident-contact summary không khớp ownership record.",
        ),
        _finding(
            "ownership_summary_mismatch",
            "release_record.ownership_status",
            "Ownership summary không khớp operational ownership record.",
        ),
    ]


def test_rollback_mismatches_follow_fixed_key_order() -> None:
    *_, record = _ready_documents()
    for key in (
        "target_release_id",
        "target_git_tag",
        "target_git_commit",
        "target_alembic_revision",
        "mode",
    ):
        record["rollback"][key] = "wrong"

    assert _only(_findings(record=record)[1], {"rollback_metadata_mismatch"}) == [
        _finding(
            "rollback_metadata_mismatch",
            f"release_record.rollback.{key}",
            "Rollback metadata không khớp deployment manifest.",
        )
        for key in (
            "target_release_id",
            "target_git_tag",
            "target_git_commit",
            "target_alembic_revision",
            "mode",
        )
    ]
