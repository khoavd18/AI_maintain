"""Deployment-storage tests grouped by storage contract dimension."""

from __future__ import annotations

from ._storage_scenarios import (
    REQUIRED_STORAGE_PATHS,
    _containment_finding,
    _finding,
    _findings,
    _missing_path_finding,
    _unknown_root_finding,
    _valid_document,
    pytest,
)


@pytest.mark.parametrize("path_name", REQUIRED_STORAGE_PATHS)
def test_unknown_root_short_circuits_path_specific_validation(path_name: str) -> None:
    document = _valid_document()
    row = document["storage"]["paths"][path_name]
    row.update(
        root="missing",
        relative_path="../escape",
        container_path="relative",
        configuration_environment="lowercase",
        retention_keep_count=0,
    )

    assert _findings(document)[1] == [_unknown_root_finding(path_name)]


@pytest.mark.parametrize("raw_row", [None, [], "path", {}, 1, True])
def test_missing_empty_or_non_mapping_required_row_has_one_exact_finding(
    raw_row: object,
) -> None:
    document = _valid_document()
    if raw_row is None:
        document["storage"]["paths"].pop("attachments")
    else:
        document["storage"]["paths"]["attachments"] = raw_row

    assert _findings(document)[1] == [_missing_path_finding("attachments")]


def test_extra_paths_and_extra_required_path_fields_are_ignored() -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["retention_keep_count"] = 0
    document["storage"]["paths"]["backups"].update(
        container_path="relative",
        configuration_environment="lowercase",
        extra="retained legacy shape",
    )
    document["storage"]["paths"]["other"] = {"not": "validated"}

    assert _findings(document)[1] == []


@pytest.mark.parametrize(
    "relative_path",
    [".", "./", "./inside", "inside//child", "inside\\child", " space "],
)
def test_current_relative_path_normalization_accepts_legacy_safe_forms(
    relative_path: str,
) -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["relative_path"] = relative_path

    assert _findings(document)[1] == []


@pytest.mark.parametrize(
    "relative_path",
    [
        None,
        "",
        " ",
        "..",
        "../escape",
        "inside/../../escape",
        "inside\\..\\escape",
        "/absolute",
        "//server/share",
        "C:/absolute",
        "C:\\absolute",
        "https://example.invalid/storage",
        "inside\x00child",
    ],
)
def test_traversal_and_cross_platform_absolute_paths_are_rejected_before_resolution(
    relative_path: object,
) -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["relative_path"] = relative_path

    assert _findings(document)[1] == [
        _containment_finding(
            "attachments",
            "Storage path phải là đường dẫn tương đối nằm trong allowed root.",
        )
    ]


def test_resolved_path_escape_uses_the_distinct_containment_message() -> None:
    class RootProbe:
        def __truediv__(self, value: str) -> TargetProbe:
            return TargetProbe(value)

    class TargetProbe:
        def __init__(self, value: str) -> None:
            self.value = value

        def resolve(self) -> TargetProbe:
            return self

        def is_relative_to(self, root: RootProbe) -> bool:
            assert isinstance(root, RootProbe)
            return self.value != "attachments"

    assert _findings(_valid_document(), RootProbe())[1] == [
        _containment_finding("attachments", "Storage path thoát khỏi allowed root.")
    ]


@pytest.mark.parametrize(
    "container_path",
    [None, "", "relative", "//app/data", "\\app\\data", "/app/../data", "/app\x00data"],
)
def test_application_paths_require_a_safe_absolute_posix_container_path(
    container_path: object,
) -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["container_path"] = container_path

    assert _findings(document)[1] == [
        _finding(
            "invalid_container_storage_path",
            "manifest.storage.paths.attachments",
            "Application storage phải có container path tuyệt đối và biến cấu hình.",
        )
    ]


@pytest.mark.parametrize("container_path", ["/", "/app//data", "/app/./data", "/app/data/"])
def test_current_container_path_normalization_accepts_legacy_safe_forms(
    container_path: str,
) -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["container_path"] = container_path

    assert _findings(document)[1] == []


@pytest.mark.parametrize(
    "configuration_environment",
    [None, "", "lowercase", " ATTACHMENT_STORAGE_ROOT", "ATTACHMENT_STORAGE_ROOT ", 1, True],
)
def test_application_configuration_environment_name_is_strict(
    configuration_environment: object,
) -> None:
    document = _valid_document()
    document["storage"]["paths"]["attachments"]["configuration_environment"] = (
        configuration_environment
    )

    assert _findings(document)[1] == [
        _finding(
            "invalid_container_storage_path",
            "manifest.storage.paths.attachments",
            "Application storage phải có container path tuyệt đối và biến cấu hình.",
        )
    ]
