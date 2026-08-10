"""Manifest and runtime integration contract tests."""

from __future__ import annotations

from ._contract_scenarios import (
    Any,
    DESIGN_READINESS_TAG,
    EXTERNAL_PILOT_NO_GO,
    GO,
    NO_GO,
    REPOSITORY_ROOT,
    _load,
    _ready_documents,
    _ready_environment,
    _ready_manifest,
    evaluate_pilot_decision,
    json,
    manifest_sha256,
    validate_deployment_manifest,
    validate_pilot_contract,
)


def test_checked_in_placeholders_keep_release_no_go_and_hash_is_bound() -> None:
    manifest = _load("pilot_manifest.json")
    release = _load("pilot_release_record.json")

    report = validate_pilot_contract(
        manifest,
        _load("operational_ownership.json"),
        _load("known_limitations.json"),
        release,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == EXTERNAL_PILOT_NO_GO
    assert "ownership_placeholder" in report.codes
    assert "critical_limitation_unaccepted" in report.codes
    assert "critical_gate_open" in report.codes
    assert release["release"]["deployment_manifest_sha256"] == manifest_sha256(manifest)


def test_checked_in_three_gate_model_keeps_organizational_authority_external() -> None:
    manifest = _load("pilot_manifest.json")
    ownership = _load("operational_ownership.json")
    limitations = _load("known_limitations.json")
    release = _load("pilot_release_record.json")

    technical = ownership["technical_stewardship"]
    assert technical["role_label"] == "Solo project developer"
    assert technical["organizational_authority"] is False
    assert set(technical["responsibilities"]) == {
        "release_preparation_owner",
        "rollback_procedure_owner",
        "backup_drill_operator",
        "database_recovery_drill_operator",
        "development_application_support",
        "security_implementation_contact",
    }
    assert {assignment["status"] for assignment in ownership["assignments"].values()} == {
        "blocked_external_dependency"
    }

    assert limitations["engineering_acknowledgement"]["status"] == (
        "DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED"
    )
    assert limitations["organizational_acceptance"]["status"] == ("BLOCKED_EXTERNAL_DEPENDENCY")
    assert all(
        row["engineering_status"] == "DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED"
        and row["organizational_acceptance_status"] == "BLOCKED_EXTERNAL_DEPENDENCY"
        and row["acceptance_status"] == "pending"
        for row in limitations["limitations"]
    )

    assert release["implementation_status"] == "COMPLETE"
    assert release["decision_gates"]["engineering_readiness"]["status"] == "PASS"
    assert release["decision_gates"]["local_rehearsal"]["status"] == "PARTIAL"
    assert release["decision_gates"]["real_company_pilot"]["display_status"] == (
        "BLOCKED — EXTERNAL DEPENDENCY"
    )
    assert release["overall_external_pilot_decision"] == EXTERNAL_PILOT_NO_GO
    assert release["final_decision"] == EXTERNAL_PILOT_NO_GO
    assert release["release"]["git_tag_recommendation"] == DESIGN_READINESS_TAG
    assert release["release"]["deployment_manifest_sha256"] == manifest_sha256(manifest)
    assert evaluate_pilot_decision(release, ownership, limitations) == NO_GO


def test_external_pilot_decision_requires_the_truthful_three_gate_model() -> None:
    manifest = _load("pilot_manifest.json")
    ownership = _load("operational_ownership.json")
    limitations = _load("known_limitations.json")
    release = _load("pilot_release_record.json")
    release["decision_gates"]["engineering_readiness"]["status"] = "FAIL"

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        release,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "declared_decision_mismatch" in report.codes


def test_manifest_detects_missing_service_duplicate_port_job_and_path_escape() -> None:
    manifest = _ready_manifest()
    manifest["services"] = [
        service for service in manifest["services"] if service["name"] != "qdrant"
    ]
    manifest["ports"][1]["host_port"] = manifest["ports"][0]["host_port"]
    manifest["scheduled_jobs"].append({"job_type": "arbitrary_shell", "enabled": True})
    manifest["storage"]["paths"]["attachments"]["relative_path"] = "../../outside"

    report = validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT)

    assert {
        "required_service_missing",
        "duplicate_port",
        "unsupported_job",
        "path_containment_violation",
    }.issubset(report.codes)


def test_manifest_rejects_scalar_rows_in_closed_contract_lists() -> None:
    manifest = _ready_manifest()
    for key in (
        "services",
        "ports",
        "volumes",
        "required_environment_variables",
        "health_endpoints",
        "scheduled_jobs",
    ):
        manifest[key].append(42)

    report = validate_deployment_manifest(manifest, repository_root=REPOSITORY_ROOT)
    malformed_scopes = {
        finding.scope for finding in report.findings if finding.code == "list_entry_not_object"
    }

    assert malformed_scopes == {
        f"manifest.{key}.{len(manifest[key]) - 1}"
        for key in (
            "services",
            "ports",
            "volumes",
            "required_environment_variables",
            "health_endpoints",
            "scheduled_jobs",
        )
    }
    assert report.decision == NO_GO


def test_runtime_observations_detect_identity_and_reachability_mismatches() -> None:
    manifest = _ready_manifest()
    probed: list[str] = []

    def probe(service: dict[str, Any]) -> bool:
        probed.append(service["name"])
        return service["name"] != "worker"

    report = validate_deployment_manifest(
        manifest,
        environment=_ready_environment(),
        actual_commit="b" * 40,
        actual_tag="wrong-tag",
        actual_tag_target_commit="c" * 40,
        actual_migration_revision="wrong-revision",
        service_probe=probe,
        repository_root=REPOSITORY_ROOT,
    )

    assert set(probed) == {"postgres", "qdrant", "api", "worker", "frontend"}
    assert {
        "release_environment_commit_mismatch",
        "release_tag_mismatch",
        "release_tag_target_commit_mismatch",
        "migration_revision_mismatch",
        "required_service_unreachable",
    }.issubset(report.codes)


def test_release_commit_is_resolved_from_exact_tag_target_without_self_reference() -> None:
    manifest = _ready_manifest()
    environment = _ready_environment()

    assert "expected_commit" not in manifest["release"]
    assert manifest["release"]["commit_resolution"] == "exact_tag_target"

    report = validate_deployment_manifest(
        manifest,
        environment=environment,
        actual_commit=environment["RELEASE_GIT_COMMIT"],
        actual_tag=environment["RELEASE_GIT_TAG"],
        actual_tag_target_commit=environment["RELEASE_GIT_COMMIT"],
        actual_migration_revision=environment["RELEASE_ALEMBIC_REVISION"],
        service_probe=lambda _service: True,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.is_valid
    assert report.decision == GO


def test_final_release_record_requires_observed_tag_target_commit() -> None:
    manifest, ownership, limitations, record = _ready_documents()

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        repository_root=REPOSITORY_ROOT,
    )

    assert report.decision == NO_GO
    assert "release_commit_observation_missing" in report.codes
    assert "release_tag_target_observation_missing" in report.codes


def test_final_release_record_requires_complete_runtime_observations() -> None:
    manifest, ownership, limitations, record = _ready_documents()

    report = validate_pilot_contract(
        manifest,
        ownership,
        limitations,
        record,
        actual_commit="a" * 40,
        repository_root=REPOSITORY_ROOT,
    )

    assert {
        "release_environment_observation_missing",
        "release_tag_observation_missing",
        "release_tag_target_observation_missing",
        "migration_observation_missing",
    }.issubset(report.codes)
    assert report.decision == NO_GO


def test_missing_pilot_secret_is_reported_without_returning_values() -> None:
    environment = _ready_environment()
    environment.pop("TOKEN_SIGNING_SECRET")
    sentinel = environment["POSTGRES_PASSWORD"]

    report = validate_deployment_manifest(
        _ready_manifest(),
        environment=environment,
        repository_root=REPOSITORY_ROOT,
    )
    serialized = json.dumps(report.as_dict())

    assert "pilot_secret_missing" in report.codes
    assert sentinel not in serialized
    assert "DATABASE_URL" not in serialized or environment["DATABASE_URL"] not in serialized


def test_compose_input_and_runtime_drift_are_blocking() -> None:
    manifest = _ready_manifest()
    manifest["required_environment_variables"] = [
        row
        for row in manifest["required_environment_variables"]
        if row["name"] != "PILOT_APP_IMAGE"
    ]
    environment = _ready_environment()
    environment["WORKER_BATCH_SIZE"] = "999"

    report = validate_deployment_manifest(
        manifest,
        environment=environment,
        repository_root=REPOSITORY_ROOT,
    )

    assert "compose_environment_not_declared" in report.codes
    assert "runtime_environment_mismatch" in report.codes


def test_restore_and_postgresql_test_suffixes_are_explicitly_separate() -> None:
    prerequisites = _load("pilot_manifest.json")["restore_prerequisites"]

    assert prerequisites["restore_database_name_suffix"] == "_restore"
    assert prerequisites["postgresql_integration_test_database_name_suffix"] == "_test"
