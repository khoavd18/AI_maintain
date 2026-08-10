"""Deployment-topology tests grouped by topology dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._topology_scenarios import (
    Finding,
    REQUIRED_SERVICES,
    _finding,
    _findings,
    _ready_manifest,
    _topology_findings,
    _validate_service_topology,
    deepcopy,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    manifest_topology_validator,
    pytest,
    signature,
)


def test_valid_topology_is_deterministic_and_does_not_mutate_input(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    original = deepcopy(document)

    first_result, first = _findings(document)
    second_result, second = _findings(document)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert document == original

    direct_findings: list[Finding] = []
    service_names = _validate_service_topology(
        document,
        dict(document["versions"]),
        direct_findings,
    )
    assert direct_findings == []
    assert service_names == REQUIRED_SERVICES
    assert list(signature(_validate_service_topology).parameters) == [
        "document",
        "versions",
        "findings",
    ]
    assert manifest_topology_validator is _validate_service_topology


@pytest.mark.parametrize("services", [None, {}, "services", 1, True])
def test_non_list_services_fail_closed_with_sorted_required_names(
    isolate_downstream: None,
    services: object,
) -> None:
    document = _ready_manifest()
    document["services"] = services

    assert _topology_findings(document) == [
        _finding("invalid_services", "manifest.services", "services phải là list."),
        *[
            _finding(
                "required_service_missing",
                f"manifest.services.{name}",
                f"Thiếu service bắt buộc: {name}.",
            )
            for name in sorted(REQUIRED_SERVICES)
        ],
        *[
            _finding(
                "port_service_unknown",
                f"manifest.ports.{port['name']}",
                "Port tham chiếu service không tồn tại.",
            )
            for port in document["ports"]
        ],
        *[
            finding
            for volume in document["volumes"]
            for finding in (
                [
                    _finding(
                        "volume_service_unknown",
                        "manifest.volumes",
                        "Volume tham chiếu service không tồn tại.",
                    )
                ]
                + (
                    [
                        _finding(
                            "volume_mount_service_unknown",
                            f"manifest.volumes.{volume['name']}",
                            "mounted_by chỉ được tham chiếu service trong closed topology.",
                        )
                    ]
                    if volume.get("mounted_by") is not None
                    else []
                )
            )
        ],
    ]


def test_scalar_service_row_reports_index_and_keeps_valid_rows(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["services"].insert(2, 42)

    assert _topology_findings(document) == [
        _finding(
            "list_entry_not_object",
            "manifest.services.2",
            "Mỗi phần tử trong danh sách contract phải là JSON object.",
        )
    ]


def test_missing_service_name_keeps_later_per_row_validation(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["services"].append({})

    assert _topology_findings(document) == [
        _finding(
            "service_name_missing",
            "manifest.services",
            "Mỗi service phải có name.",
        ),
        _finding(
            "service_not_required",
            "manifest.services.None",
            "Mỗi service trong closed pilot topology phải được đánh dấu required=true.",
        ),
        _finding(
            "service_version_reference_invalid",
            "manifest.services.None",
            "Service phải tham chiếu component version đã khai báo.",
        ),
    ]


def test_duplicate_service_is_reported_once_without_hiding_rows(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["services"].append(deepcopy(document["services"][0]))
    name = document["services"][0]["name"]

    assert _topology_findings(document) == [
        _finding(
            "duplicate_service",
            f"manifest.services.{name}",
            "service bị khai báo trùng.",
        )
    ]


def test_missing_and_unsupported_services_are_sorted_before_row_checks(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["services"] = [service for service in document["services"] if service["name"] != "api"]
    document["services"].append({"name": "custom", "required": True, "version_ref": "application"})

    findings = _topology_findings(document)

    assert findings[0:2] == [
        _finding(
            "required_service_missing",
            "manifest.services.api",
            "Thiếu service bắt buộc: api.",
        ),
        _finding(
            "unsupported_service",
            "manifest.services.custom",
            "Service ngoài contract PM9: custom.",
        ),
    ]
    assert any(finding.code == "port_service_unknown" for finding in findings[2:])


@pytest.mark.parametrize("required", [None, False, 0, 1, "true"])
def test_service_required_flag_requires_true_singleton(
    isolate_downstream: None,
    required: object,
) -> None:
    document = _ready_manifest()
    document["services"][0]["required"] = required
    name = document["services"][0]["name"]

    assert _topology_findings(document) == [
        _finding(
            "service_not_required",
            f"manifest.services.{name}",
            "Mỗi service trong closed pilot topology phải được đánh dấu required=true.",
        )
    ]


@pytest.mark.parametrize("version_ref", [None, "", " application", "unknown", 1, True])
def test_service_version_reference_uses_exact_version_mapping_membership(
    isolate_downstream: None,
    version_ref: object,
) -> None:
    document = _ready_manifest()
    document["services"][0]["version_ref"] = version_ref
    name = document["services"][0]["name"]

    assert _topology_findings(document) == [
        _finding(
            "service_version_reference_invalid",
            f"manifest.services.{name}",
            "Service phải tham chiếu component version đã khai báo.",
        )
    ]


def test_extra_version_key_is_a_valid_service_reference(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["versions"]["custom"] = "1"
    document["services"][0]["version_ref"] = "custom"

    assert _topology_findings(document) == []


def test_unsupported_service_is_still_known_to_ports_and_volumes(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["services"].append({"name": "custom", "required": True, "version_ref": "application"})
    document["ports"][0]["service"] = "custom"
    document["volumes"][0]["service"] = "custom"

    assert _topology_findings(document) == [
        _finding(
            "unsupported_service",
            "manifest.services.custom",
            "Service ngoài contract PM9: custom.",
        )
    ]
