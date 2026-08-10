"""Repository-binding tests grouped by checked-in surface."""

from __future__ import annotations

from ._repository_contract_scenarios import (
    FRONTEND_VERSION,
    Finding,
    NEXT_VERSION,
    Path,
    _finding,
    _findings,
    _valid_document,
    _validate_repository_contract,
    _write_repository,
    pytest,
)


@pytest.mark.parametrize("package", [[], None, "package", 1, True])
def test_valid_json_non_object_frontend_package_keeps_attribute_error_boundary(
    tmp_path: Path,
    package: object,
) -> None:
    _write_repository(tmp_path, package=package)
    findings: list[Finding] = []

    with pytest.raises(AttributeError):
        _validate_repository_contract(_valid_document(), tmp_path, findings)
    assert findings == []


def test_frontend_version_and_next_mismatches_accumulate_in_order(tmp_path: Path) -> None:
    _write_repository(
        tmp_path,
        package={"version": f" {FRONTEND_VERSION} ", "dependencies": {"next": f" {NEXT_VERSION} "}},
    )

    assert _findings(_valid_document(), tmp_path)[1] == [
        _finding(
            "frontend_version_mismatch",
            "manifest.versions.frontend",
            "Frontend version trong manifest không khớp package metadata.",
        ),
        _finding(
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        ),
    ]


@pytest.mark.parametrize("dependencies", [None, [], "dependencies", 1, True])
def test_non_mapping_frontend_dependencies_only_mismatch_next(
    tmp_path: Path,
    dependencies: object,
) -> None:
    _write_repository(
        tmp_path,
        package={"version": FRONTEND_VERSION, "dependencies": dependencies},
    )

    assert _findings(_valid_document(), tmp_path)[1] == [
        _finding(
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        )
    ]


def test_missing_release_and_versions_accumulate_all_owned_mismatches(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["release"] = None
    document["versions"] = None

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "application_version_mismatch",
            "manifest.versions.application",
            "Application version trong manifest không khớp runtime.",
        ),
        _finding(
            "canonical_migration_revision_mismatch",
            "manifest.release.alembic_revision",
            "Alembic revision trong manifest không khớp schema head của ứng dụng.",
        ),
        _finding(
            "frontend_version_mismatch",
            "manifest.versions.frontend",
            "Frontend version trong manifest không khớp package metadata.",
        ),
        _finding(
            "nextjs_version_mismatch",
            "manifest.versions.nextjs",
            "Next.js version trong manifest không khớp package metadata.",
        ),
    ]
