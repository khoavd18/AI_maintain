"""Decision and operational-governance integration contract tests."""

from __future__ import annotations

from ._contract_scenarios import (
    CONDITIONAL_GO,
    DESIGN_READINESS_TAG,
    GO,
    NO_GO,
    REPOSITORY_ROOT,
    _ready_documents,
    _ready_environment,
    _ready_limitations,
    _ready_ownership,
    evaluate_pilot_decision,
    validate_pilot_contract,
)


def test_complete_evidence_is_go_and_result_is_deterministic() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    kwargs = {
        "environment": _ready_environment(),
        "actual_commit": "a" * 40,
        "actual_tag": DESIGN_READINESS_TAG,
        "actual_tag_target_commit": "a" * 40,
        "actual_migration_revision": "20260726_0008",
        "service_probe": lambda _service: True,
        "repository_root": REPOSITORY_ROOT,
    }

    first = validate_pilot_contract(manifest, ownership, limitations, record, **kwargs)
    second = validate_pilot_contract(manifest, ownership, limitations, record, **kwargs)

    assert first.decision == GO
    assert first.is_valid
    assert first.as_dict() == second.as_dict()


def test_missing_incident_path_and_unaccepted_critical_limitation_block_go() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    ownership["incident_communication"]["status"] = "unconfigured"
    limitations["limitations"][0]["acceptance_status"] = "pending"

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_required_limitation_cannot_be_downgraded_from_critical() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    limitations["limitations"][0]["critical"] = False
    record["known_limitations_acceptance_status"] = "pending"
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert "required_limitation_weakened" in report.codes
    assert report.decision == NO_GO


def test_invalid_timezone_and_duplicate_escalation_steps_block_readiness() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    ownership["support_coverage"]["timezone"] = "Mars/Olympus_Mons"
    ownership["escalation_path"]["steps"].append(dict(ownership["escalation_path"]["steps"][0]))
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert {
        "support_timezone_invalid",
        "duplicate_escalation_step",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_pending_governance_records_and_missing_approval_evidence_block_go() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    ownership["record_status"] = "pending_owner_input"
    limitations["record_status"] = "pending_business_acceptance"
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "ownership_record_not_approved" in report.codes
    assert "limitations_record_not_accepted" in report.codes

    ownership = _ready_ownership()
    limitations = _ready_limitations()
    ownership["support_coverage"]["approval_evidence_links"] = []
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_decision_fails_closed_for_malformed_or_duplicate_rows() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"].append(42)
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"].append(dict(record["gates"][0]))
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["gates"][0]["critical"] = False
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    _manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [42]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_bounded_noncritical_risk_is_conditional_go() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    record["open_risks"] = [
        {
            "id": "bounded_display_risk",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"] = [
        {
            "risk_or_limitation_id": "bounded_display_risk",
            "description": "Một nhãn pilot cần được làm rõ.",
            "owner_role": assigned_owner_role,
            "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == CONDITIONAL_GO

    record["conditions"][0]["owner_role"] = "PENDING_ASSIGNMENT"
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_condition_owner_must_match_an_assigned_operational_role() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [
        {
            "id": "bounded_display_risk",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"] = [
        {
            "risk_or_limitation_id": "bounded_display_risk",
            "description": "Một nhãn pilot cần được làm rõ.",
            "owner_role": "shadow_support_role",
            "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    ownership["assignments"]["shadow_contact"] = {
        "assigned_role": "shadow_support_role",
        "status": "assigned",
    }
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    record["final_decision"] = NO_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag=DESIGN_READINESS_TAG,
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO


def test_optional_limitation_with_invalid_status_fails_closed() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    limitations["limitations"].append(
        {
            "id": "optional_cosmetic_limitation",
            "critical": False,
            "description": "Giới hạn hiển thị không ảnh hưởng tính toàn vẹn.",
            "operational_consequence": "Operator có thể cần đọc hướng dẫn bổ sung.",
            "mitigation": "Giữ hướng dẫn trong runbook pilot.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "acceptance_status": "unknown",
            "review_trigger": "Trước khi mở rộng nhóm pilot.",
        }
    )
    record["conditions"] = [
        {
            "risk_or_limitation_id": "optional_cosmetic_limitation",
            "description": "Điều kiện pilot có giới hạn.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/optional-limitation.json"],
        }
    ]

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_non_string_limitation_statuses_fail_closed_without_type_error() -> None:
    for invalid_status in (None, [], {}):
        manifest, ownership, limitations, record = _ready_documents()
        limitations["limitations"].append(
            {
                "id": "optional_cosmetic_limitation",
                "critical": False,
                "description": "Giới hạn hiển thị không ảnh hưởng tính toàn vẹn.",
                "operational_consequence": "Operator có thể cần đọc hướng dẫn bổ sung.",
                "mitigation": "Giữ hướng dẫn trong runbook pilot.",
                "owner_role": ownership["assignments"]["application_support_contact"][
                    "assigned_role"
                ],
                "acceptance_status": invalid_status,
                "review_trigger": "Trước khi mở rộng nhóm pilot.",
            }
        )
        record["final_decision"] = NO_GO

        assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

        report = validate_pilot_contract(
            manifest,
            ownership,
            limitations,
            record,
            environment=_ready_environment(),
            actual_commit="a" * 40,
            actual_tag=DESIGN_READINESS_TAG,
            actual_tag_target_commit="a" * 40,
            actual_migration_revision="20260726_0008",
            service_probe=lambda _service: True,
            repository_root=REPOSITORY_ROOT,
        )

        assert "limitation_acceptance_invalid" in report.codes
        assert report.decision == NO_GO


def test_incomplete_or_unknown_risk_fields_cannot_yield_conditional_go() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    bounded_condition = {
        "risk_or_limitation_id": "bounded_display_risk",
        "description": "Một nhãn pilot cần được làm rõ.",
        "owner_role": assigned_owner_role,
        "mitigation": "Hướng dẫn operator đã được ghi trong pilot runbook.",
        "review_trigger": "Trước khi mở rộng nhóm pilot.",
        "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
        "evidence_links": ["evidence/conditions/bounded-display-risk.json"],
    }
    baseline = {
        "id": "bounded_display_risk",
        "severity": "low",
        "category": "usability",
        "status": "open",
    }
    record["conditions"] = [bounded_condition]

    for field, invalid_value in (
        ("status", "unknown"),
        ("severity", "unknown"),
        ("category", "unknown"),
    ):
        risk = dict(baseline)
        risk[field] = invalid_value
        record["open_risks"] = [risk]
        assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    record["open_risks"] = [{"id": "bounded_display_risk"}]
    record["final_decision"] = NO_GO
    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert {
        "risk_status_invalid",
        "risk_severity_invalid",
        "risk_category_invalid",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_closed_protected_risk_cannot_be_skipped_in_open_risk_register() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["open_risks"] = [
        {
            "id": "critical_auth_risk",
            "severity": "critical",
            "category": "authorization",
            "status": "closed",
        }
    ]
    record["final_decision"] = GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag=DESIGN_READINESS_TAG,
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO
    assert "risk_status_invalid" in report.codes
    assert report.decision == NO_GO


def test_orphan_condition_and_cross_register_id_collision_fail_closed() -> None:
    _manifest, ownership, limitations, record = _ready_documents()
    record["conditions"] = [
        {
            "risk_or_limitation_id": "nonexistent_item",
            "description": "Điều kiện không có risk hoặc limitation nguồn.",
            "owner_role": ownership["assignments"]["application_support_contact"]["assigned_role"],
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/orphan.json"],
        }
    ]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO

    record["open_risks"] = [
        {
            "id": limitations["limitations"][0]["id"],
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"][0]["risk_or_limitation_id"] = record["open_risks"][0]["id"]
    assert evaluate_pilot_decision(record, ownership, limitations) == NO_GO


def test_placeholder_risk_limitation_and_condition_ids_fail_closed() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    assigned_owner_role = ownership["assignments"]["application_support_contact"]["assigned_role"]
    limitations["limitations"].append(
        {
            "id": "PENDING_LIMITATION",
            "critical": False,
            "description": "Giới hạn phụ trong phạm vi pilot.",
            "operational_consequence": "Operator cần theo dõi thủ công.",
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "owner_role": assigned_owner_role,
            "acceptance_status": "pending",
            "review_trigger": "Trước khi mở rộng pilot.",
        }
    )
    record["conditions"] = [
        {
            "risk_or_limitation_id": "PENDING_LIMITATION",
            "description": "Điều kiện pilot có giới hạn.",
            "owner_role": assigned_owner_role,
            "mitigation": "Giữ phạm vi pilot có giới hạn.",
            "review_trigger": "Trước khi mở rộng pilot.",
            "pilot_scope_limit": "Chỉ nhóm internal pilot đã phê duyệt.",
            "evidence_links": ["evidence/conditions/limitation.json"],
        }
    ]
    record["final_decision"] = CONDITIONAL_GO

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        environment=_ready_environment(),
        actual_commit="a" * 40,
        actual_tag=DESIGN_READINESS_TAG,
        actual_tag_target_commit="a" * 40,
        actual_migration_revision="20260726_0008",
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert "limitation_id_missing" in report.codes
    assert report.decision == NO_GO

    record["open_risks"] = [
        {
            "id": "PENDING_RISK",
            "severity": "low",
            "category": "usability",
            "status": "open",
        }
    ]
    record["conditions"][0]["risk_or_limitation_id"] = "PENDING_RISK"
    assert evaluate_pilot_decision(record, ownership, _ready_limitations()) == NO_GO
