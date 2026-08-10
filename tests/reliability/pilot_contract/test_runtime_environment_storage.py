"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    Any,
    Path,
    REPOSITORY_ROOT,
    _finding,
    _findings,
    _only,
    _ready_environment,
    pytest,
)


def test_relative_or_repository_local_storage_roots_are_rejected() -> None:
    environment = _ready_environment()
    environment["PILOT_ALLOWED_DATA_ROOT"] = "relative/data"
    environment["PILOT_BACKUP_ROOT"] = str(REPOSITORY_ROOT / "backups")

    assert _only(
        _findings(environment=environment)[1],
        {"environment_root_containment_violation"},
    ) == [
        _finding(
            "environment_root_containment_violation",
            "environment.PILOT_ALLOWED_DATA_ROOT",
            "PILOT_ALLOWED_DATA_ROOT phải là absolute root nằm ngoài repository.",
        ),
        _finding(
            "environment_root_containment_violation",
            "environment.PILOT_BACKUP_ROOT",
            "PILOT_BACKUP_ROOT phải là absolute root nằm ngoài repository.",
        ),
    ]


def test_missing_storage_root_values_are_skipped_without_root_finding() -> None:
    environment = _ready_environment()
    environment["PILOT_ALLOWED_DATA_ROOT"] = ""
    environment["PILOT_BACKUP_ROOT"] = ""

    assert not {
        "environment_root_containment_violation",
        "storage_roots_overlap",
    } & {finding.code for finding in _findings(environment=environment)[1]}


def test_equal_and_nested_storage_roots_have_one_backup_scoped_finding() -> None:
    environment = _ready_environment()
    data_root = REPOSITORY_ROOT.parent / "pm9-overlap"
    environment["PILOT_ALLOWED_DATA_ROOT"] = str(data_root)
    environment["PILOT_BACKUP_ROOT"] = str(data_root / "backup")

    assert _only(_findings(environment=environment)[1], {"storage_roots_overlap"}) == [
        _finding(
            "storage_roots_overlap",
            "environment.PILOT_BACKUP_ROOT",
            "Pilot data root và backup root phải tách biệt, không lồng nhau.",
        )
    ]


def test_storage_root_resolution_exception_becomes_containment_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _ready_environment()
    target = Path(environment["PILOT_ALLOWED_DATA_ROOT"])
    original_resolve = Path.resolve

    def failing_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self == target:
            raise RuntimeError("loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failing_resolve)

    assert _only(
        _findings(environment=environment)[1],
        {"environment_root_containment_violation"},
    ) == [
        _finding(
            "environment_root_containment_violation",
            "environment.PILOT_ALLOWED_DATA_ROOT",
            "PILOT_ALLOWED_DATA_ROOT phải là absolute root nằm ngoài repository.",
        )
    ]


def test_container_path_environment_mismatch_ignores_backup_row() -> None:
    environment = _ready_environment()
    environment["ATTACHMENT_STORAGE_ROOT"] = "/different"

    assert _only(
        _findings(environment=environment)[1], {"container_path_environment_mismatch"}
    ) == [
        _finding(
            "container_path_environment_mismatch",
            "environment.ATTACHMENT_STORAGE_ROOT",
            "ATTACHMENT_STORAGE_ROOT không khớp container storage path.",
        )
    ]


def test_backup_retention_uses_integer_match_helper() -> None:
    environment = _ready_environment()
    environment["PILOT_BACKUP_RETENTION_COUNT"] = "8"

    assert _only(_findings(environment=environment)[1], {"runtime_environment_mismatch"})[-1:] == [
        _finding(
            "runtime_environment_mismatch",
            "environment.PILOT_BACKUP_RETENTION_COUNT",
            "PILOT_BACKUP_RETENTION_COUNT phải là số nguyên khớp deployment manifest.",
        )
    ]
