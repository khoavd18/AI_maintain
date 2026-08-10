"""Deployment-storage tests grouped by storage contract dimension."""

from __future__ import annotations

from ._storage_scenarios import (
    REQUIRED_STORAGE_PATHS,
    _finding,
    _findings,
    _missing_path_finding,
    _unknown_root_finding,
    _valid_document,
    _validate_storage,
    deepcopy,
    manifest_module,
    manifest_storage_validator,
    pytest,
    signature,
)


def test_valid_storage_contract_is_deterministic_and_not_mutated() -> None:
    document = _valid_document()
    original = deepcopy(document)

    first_result, first = _findings(document)
    second_result, second = _findings(document)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert document == original
    assert list(signature(_validate_storage).parameters) == [
        "document",
        "repository_root",
        "findings",
    ]
    assert manifest_module._validate_storage is _validate_storage
    assert manifest_storage_validator is _validate_storage


@pytest.mark.parametrize("raw_storage", [None, [], "storage", 1, True])
def test_missing_or_non_mapping_storage_fails_closed_in_exact_order(
    raw_storage: object,
) -> None:
    document = {} if raw_storage is None else {"storage": raw_storage}

    assert _findings(document)[1] == [
        _finding(
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        ),
        *[_missing_path_finding(name) for name in REQUIRED_STORAGE_PATHS],
    ]


@pytest.mark.parametrize("raw_paths", [None, [], "paths", 1, True])
def test_missing_or_non_mapping_paths_report_required_names_in_contract_order(
    raw_paths: object,
) -> None:
    document = _valid_document()
    if raw_paths is None:
        document["storage"].pop("paths")
    else:
        document["storage"]["paths"] = raw_paths

    assert _findings(document)[1] == [
        _missing_path_finding(name) for name in REQUIRED_STORAGE_PATHS
    ]


def test_empty_allowed_roots_short_circuit_all_path_details() -> None:
    document = _valid_document()
    document["storage"]["allowed_roots"] = {}
    for row in document["storage"]["paths"].values():
        row["relative_path"] = "../escape"
        row["container_path"] = "relative"
        row["configuration_environment"] = "lowercase"
        row["retention_keep_count"] = 0

    assert _findings(document)[1] == [
        _finding(
            "allowed_roots_missing",
            "manifest.storage",
            "Storage contract phải khai báo allowed_roots.",
        ),
        *[_unknown_root_finding(name) for name in REQUIRED_STORAGE_PATHS],
    ]


@pytest.mark.parametrize(
    "invalid_root",
    [
        None,
        [],
        "root",
        {},
        {
            "environment_variable": "pilot_allowed_data_root",
            "scope": "host",
            "outside_repository": True,
        },
        {
            "environment_variable": " PILOT_ALLOWED_DATA_ROOT",
            "scope": "host",
            "outside_repository": True,
        },
        {
            "environment_variable": "PILOT_ALLOWED_DATA_ROOT ",
            "scope": "host",
            "outside_repository": True,
        },
        {
            "environment_variable": "PILOT_ALLOWED_DATA_ROOT",
            "scope": "container",
            "outside_repository": True,
        },
        {
            "environment_variable": "PILOT_ALLOWED_DATA_ROOT",
            "scope": "host",
            "outside_repository": 1,
        },
        {
            "environment_variable": "PILOT_ALLOWED_DATA_ROOT",
            "scope": "host",
            "outside_repository": True,
            "extra": False,
        },
    ],
)
def test_allowed_root_shape_is_strict_and_invalid_roots_are_not_resolved(
    invalid_root: object,
) -> None:
    document = _valid_document()
    document["storage"]["allowed_roots"]["data"] = invalid_root

    assert _findings(document)[1] == [
        _finding(
            "invalid_allowed_root",
            "manifest.storage.allowed_roots.data",
            "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
        ),
        *[
            _unknown_root_finding(name)
            for name in ("attachments", "analytics_source", "analytics_output")
        ],
    ]


def test_invalid_allowed_roots_follow_mapping_insertion_order() -> None:
    document = _valid_document()
    document["storage"]["allowed_roots"] = {
        "z-last": {},
        "a-first": {},
        **document["storage"]["allowed_roots"],
    }

    assert _findings(document)[1] == [
        _finding(
            "invalid_allowed_root",
            "manifest.storage.allowed_roots.z-last",
            "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
        ),
        _finding(
            "invalid_allowed_root",
            "manifest.storage.allowed_roots.a-first",
            "Allowed root phải tham chiếu biến môi trường host nằm ngoài repository.",
        ),
    ]


def test_root_names_are_open_and_extra_valid_roots_are_accepted() -> None:
    document = _valid_document()
    roots = document["storage"]["allowed_roots"]
    roots["custom-data"] = roots.pop("data")
    roots["custom-backup"] = roots.pop("backup")
    roots["unused"] = {
        "environment_variable": "UNUSED_STORAGE_ROOT",
        "scope": "host",
        "outside_repository": True,
    }
    for name in ("attachments", "analytics_source", "analytics_output"):
        document["storage"]["paths"][name]["root"] = "custom-data"
    document["storage"]["paths"]["backups"]["root"] = "custom-backup"

    assert _findings(document)[1] == []
