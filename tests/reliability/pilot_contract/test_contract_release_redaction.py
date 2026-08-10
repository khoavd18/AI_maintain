"""Contract-dimension tests split from the historical integration suite."""

from __future__ import annotations

from ._contract_scenarios import (
    DESIGN_READINESS_TAG,
    NO_GO,
    REPOSITORY_ROOT,
    _ready_documents,
    _ready_environment,
    json,
    redact_release_record,
    validate_pilot_contract,
)


def test_release_record_requires_evidence_and_matching_rollback_metadata() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    record["gates"][0]["evidence_links"] = []
    record["rollback"]["target_git_tag"] = "wrong-tag"
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

    assert "gate_evidence_missing" in report.codes
    assert "rollback_metadata_mismatch" in report.codes
    assert report.decision == NO_GO


def test_release_redactor_removes_credentials_contacts_and_local_paths() -> None:
    redacted = redact_release_record(
        {
            "password": "secret-value",
            "artifact_path": "C:\\Users\\Example\\private.json",
            "connection": "postgresql://pilot:secret@database/pilot",
            "email": "person@example.com",
            "safe_link": "evidence/releases/pm9.json",
        }
    )

    serialized = json.dumps(redacted)
    assert "secret-value" not in serialized
    assert "Example" not in serialized
    assert "person@example.com" not in serialized
    assert redacted["safe_link"] == "evidence/releases/pm9.json"
