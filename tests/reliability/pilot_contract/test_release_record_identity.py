"""Release-record tests grouped by validation capability."""

from __future__ import annotations

from ._release_record_scenarios import (
    OBSERVED_COMMIT,
    _finding,
    _findings,
    _only,
    _ready_documents,
    _validate_release_record,
    contract_release_record_validator,
    deepcopy,
    pytest,
    signature,
)


def test_ready_release_record_is_deterministic_immutable_and_has_stable_signature() -> None:
    manifest, ownership, limitations, record = _ready_documents()
    originals = deepcopy((manifest, ownership, limitations, record))

    first_result, first = _findings(
        record=record,
        manifest=manifest,
        ownership=ownership,
        limitations=limitations,
    )
    second_result, second = _findings(
        record=record,
        manifest=manifest,
        ownership=ownership,
        limitations=limitations,
    )

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert (manifest, ownership, limitations, record) == originals
    assert list(signature(_validate_release_record).parameters) == [
        "record",
        "manifest",
        "ownership",
        "limitations",
        "digest",
        "actual_commit",
        "findings",
    ]
    assert contract_release_record_validator is _validate_release_record


def test_missing_unused_required_keys_are_sorted_first() -> None:
    *_, record = _ready_documents()
    for key in ("conditions", "final_decision"):
        record.pop(key)

    assert _only(_findings(record=record)[1], {"required_key_missing"}) == [
        _finding(
            "required_key_missing",
            f"release_record.{key}",
            f"Thiếu required key: {key}.",
        )
        for key in ("conditions", "final_decision")
    ]


@pytest.mark.parametrize("schema", [None, "", " ", True, 1.0, [], {}])
def test_release_schema_version_is_strict(schema: object) -> None:
    *_, record = _ready_documents()
    record["schema_version"] = schema

    assert _only(_findings(record=record)[1], {"invalid_schema_version"}) == [
        _finding(
            "invalid_schema_version",
            "release_record",
            "Release record phải có schema_version.",
        )
    ]


def test_kind_status_timestamp_and_production_claim_findings_keep_order() -> None:
    *_, record = _ready_documents()
    record.update(
        record_kind="wrong",
        record_status="final",
        generated_at_utc="not-utc",
        production_readiness_claim=True,
    )

    assert _only(
        _findings(record=record)[1],
        {
            "invalid_release_record_kind",
            "release_timestamp_missing",
            "production_readiness_claim_forbidden",
        },
    ) == [
        _finding(
            "invalid_release_record_kind",
            "release_record.record_kind",
            "Release record kind không khớp internal-pilot contract.",
        ),
        _finding(
            "release_timestamp_missing",
            "release_record.generated_at_utc",
            "Final release record phải có UTC generation timestamp.",
        ),
        _finding(
            "production_readiness_claim_forbidden",
            "release_record",
            "Release record internal pilot không được tuyên bố production readiness.",
        ),
    ]


def test_draft_status_skips_timestamp_validation() -> None:
    *_, record = _ready_documents()
    record["record_status"] = "draft"
    record["generated_at_utc"] = "invalid"

    assert _only(
        _findings(record=record)[1],
        {"release_record_not_final", "release_timestamp_missing"},
    ) == [
        _finding(
            "release_record_not_final",
            "release_record.record_status",
            "Pilot release record vẫn là draft.",
        )
    ]


def test_release_identity_fields_accumulate_in_mapping_order() -> None:
    *_, record = _ready_documents()
    for key in (
        "release_name",
        "git_tag_recommendation",
        "migration_revision",
        "deployment_manifest_sha256",
    ):
        record["release"][key] = "wrong"

    assert _only(_findings(record=record)[1], {"release_record_identity_mismatch"}) == [
        _finding(
            "release_record_identity_mismatch",
            f"release_record.release.{key}",
            f"Release record field {key} không khớp deployment manifest.",
        )
        for key in (
            "release_name",
            "git_tag_recommendation",
            "migration_revision",
            "deployment_manifest_sha256",
        )
    ]


@pytest.mark.parametrize(
    ("recorded_commit", "actual_commit", "code"),
    [
        ("TBD", OBSERVED_COMMIT, "release_record_commit_pending"),
        ("g" * 40, OBSERVED_COMMIT, "release_record_commit_invalid"),
        ("b" * 40, OBSERVED_COMMIT, "release_record_commit_mismatch"),
        (OBSERVED_COMMIT, None, "release_commit_observation_missing"),
    ],
)
def test_release_commit_branch_is_exclusive(
    recorded_commit: str,
    actual_commit: str | None,
    code: str,
) -> None:
    *_, record = _ready_documents()
    record["release"]["git_commit"] = recorded_commit

    findings = _only(
        _findings(record=record, actual_commit=actual_commit)[1],
        {
            "release_record_commit_pending",
            "release_record_commit_invalid",
            "release_record_commit_mismatch",
            "release_commit_observation_missing",
        },
    )
    assert [finding.code for finding in findings] == [code]


def test_version_job_and_alert_summaries_keep_order_and_exact_equality() -> None:
    manifest, _, _, record = _ready_documents()
    record["application_versions"] = {}
    record["database_version"] = "wrong"
    record["enabled_jobs"] = [*record["enabled_jobs"], "unexpected_job"]
    record["configured_alert_thresholds"] = {**manifest["operational_alerts"], "extra": 1}

    assert _only(
        _findings(record=record, manifest=manifest)[1],
        {
            "release_version_mismatch",
            "database_version_mismatch",
            "enabled_jobs_mismatch",
            "alert_threshold_mismatch",
        },
    ) == [
        _finding(
            "release_version_mismatch",
            "release_record.application_versions",
            "Application versions không khớp deployment manifest.",
        ),
        _finding(
            "database_version_mismatch",
            "release_record.database_version",
            "Database version không khớp deployment manifest.",
        ),
        _finding(
            "enabled_jobs_mismatch",
            "release_record.enabled_jobs",
            "Enabled jobs không khớp deployment manifest.",
        ),
        _finding(
            "alert_threshold_mismatch",
            "release_record.configured_alert_thresholds",
            "Alert thresholds không khớp deployment manifest.",
        ),
    ]
