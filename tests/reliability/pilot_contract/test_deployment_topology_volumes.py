"""Deployment-topology tests grouped by topology dimension."""

# ruff: noqa: F811 - imported pytest fixture is named by test parameters

from __future__ import annotations

from ._topology_scenarios import (
    _finding,
    _ready_manifest,
    _topology_findings,
    deepcopy,
    isolate_downstream,  # noqa: F401 - registers the split-suite fixture
    pytest,
)


def test_scalar_volume_row_reports_index_without_hiding_valid_rows(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    document["volumes"].insert(3, 42)

    assert _topology_findings(document) == [
        _finding(
            "list_entry_not_object",
            "manifest.volumes.3",
            "Mỗi phần tử trong danh sách contract phải là JSON object.",
        )
    ]


def test_missing_and_duplicate_volume_names_are_characterized(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    unnamed = deepcopy(document["volumes"][0])
    unnamed.pop("name")
    duplicate = deepcopy(document["volumes"][1])
    document["volumes"].extend([unnamed, duplicate])

    assert _topology_findings(document) == [
        _finding(
            "volume_name_missing",
            "manifest.volumes",
            "Mỗi volume phải có name.",
        ),
        _finding(
            "duplicate_volume",
            f"manifest.volumes.{duplicate['name']}",
            "volume bị khai báo trùng.",
        ),
    ]


def test_missing_volume_purpose_has_exact_scope(isolate_downstream: None) -> None:
    document = _ready_manifest()
    purpose = document["volumes"][0]["purpose"]
    document["volumes"] = [volume for volume in document["volumes"] if volume["purpose"] != purpose]

    assert _topology_findings(document) == [
        _finding(
            "required_volume_missing",
            f"manifest.volumes.{purpose}",
            f"Thiếu persistent volume cho {purpose}.",
        )
    ]


def test_volume_errors_accumulate_in_service_storage_mount_persistence_order(
    isolate_downstream: None,
) -> None:
    document = _ready_manifest()
    volume = document["volumes"][0]
    volume.update(
        service="missing",
        kind="host_bind",
        storage_path_ref="missing",
        mounted_by=[],
        persistent=False,
    )

    assert _topology_findings(document) == [
        _finding(
            "volume_service_unknown",
            "manifest.volumes",
            "Volume tham chiếu service không tồn tại.",
        ),
        _finding(
            "volume_storage_path_unknown",
            f"manifest.volumes.{volume['name']}",
            "Host storage phải tham chiếu storage path đã khai báo.",
        ),
        _finding(
            "volume_mount_service_unknown",
            f"manifest.volumes.{volume['name']}",
            "mounted_by chỉ được tham chiếu service trong closed topology.",
        ),
        _finding(
            "volume_not_persistent",
            "manifest.volumes",
            "Volume pilot phải được đánh dấu persistent=true.",
        ),
    ]


@pytest.mark.parametrize("kind", [None, "", "HOST_BIND", " host_bind", 1, True])
def test_volume_kind_is_exact(
    isolate_downstream: None,
    kind: object,
) -> None:
    document = _ready_manifest()
    document["volumes"][0]["kind"] = kind
    name = document["volumes"][0]["name"]

    assert _topology_findings(document) == [
        _finding(
            "invalid_volume_kind",
            f"manifest.volumes.{name}",
            "Persistent storage phải khai báo loại volume được hỗ trợ.",
        )
    ]


def test_named_volume_ignores_storage_path_reference(isolate_downstream: None) -> None:
    document = _ready_manifest()
    volume = document["volumes"][0]
    volume["kind"] = "compose_named_volume"
    volume["storage_path_ref"] = "missing"

    assert _topology_findings(document) == []


@pytest.mark.parametrize("mounted_by", [[], "api", ["missing"], ["api", "missing"], 1, True])
def test_mounted_by_requires_nonempty_known_service_list_when_present(
    isolate_downstream: None,
    mounted_by: object,
) -> None:
    document = _ready_manifest()
    document["volumes"][0]["mounted_by"] = mounted_by
    name = document["volumes"][0]["name"]

    assert _topology_findings(document) == [
        _finding(
            "volume_mount_service_unknown",
            f"manifest.volumes.{name}",
            "mounted_by chỉ được tham chiếu service trong closed topology.",
        )
    ]


@pytest.mark.parametrize("mounted_by", [None, ["api"], ["api", "api"]])
def test_mounted_by_none_and_duplicate_known_services_are_accepted(
    isolate_downstream: None,
    mounted_by: object,
) -> None:
    document = _ready_manifest()
    document["volumes"][0]["mounted_by"] = mounted_by

    assert _topology_findings(document) == []


@pytest.mark.parametrize("persistent", [None, False, 0, 1, "true"])
def test_volume_persistent_requires_true_singleton(
    isolate_downstream: None,
    persistent: object,
) -> None:
    document = _ready_manifest()
    document["volumes"][0]["persistent"] = persistent

    assert _topology_findings(document) == [
        _finding(
            "volume_not_persistent",
            "manifest.volumes",
            "Volume pilot phải được đánh dấu persistent=true.",
        )
    ]


def test_unknown_topology_fields_are_ignored(isolate_downstream: None) -> None:
    document = _ready_manifest()
    document["services"][0]["unknown"] = True
    document["ports"][0]["unknown"] = True
    document["volumes"][0]["unknown"] = True

    assert _topology_findings(document) == []
