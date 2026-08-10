"""Repository-binding tests grouped by checked-in surface."""

from __future__ import annotations

from ._repository_contract_scenarios import (
    APPLICATION_VERSION,
    Any,
    CANONICAL_SCHEMA_REVISION,
    COMPOSE_NAME,
    Finding,
    Path,
    _finding,
    _findings,
    _valid_document,
    _validate_repository_contract,
    _write_repository,
    pytest,
)


def test_application_and_schema_version_mismatches_accumulate_in_order(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["versions"]["application"] = f" {APPLICATION_VERSION} "
    document["release"]["alembic_revision"] = f" {CANONICAL_SCHEMA_REVISION} "

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
    ]


def test_runtime_image_mismatches_follow_source_expectation_order(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["images"] = {
        "python_base": "python:other",
        "node_base": "node:other",
        "postgresql": "postgres:other",
        "qdrant": "qdrant:other",
    }

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "runtime_image_mismatch",
            "manifest.images.python_base",
            "Image trong manifest không khớp deployment source.",
        ),
        _finding(
            "runtime_image_mismatch",
            "manifest.images.node_base",
            "Image trong manifest không khớp deployment source.",
        ),
        _finding(
            "runtime_image_mismatch",
            "manifest.images.postgresql",
            "Image trong manifest không khớp deployment source.",
        ),
        _finding(
            "runtime_image_mismatch",
            "manifest.images.qdrant",
            "Image trong manifest không khớp deployment source.",
        ),
    ]


def test_missing_image_fields_keep_legacy_prefix_substring_acceptance(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["images"] = {}

    assert _findings(document, tmp_path)[1] == []


def test_runtime_source_os_errors_accumulate_and_package_validation_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    compose_path = tmp_path / COMPOSE_NAME
    original_read_text = Path.read_text
    compose_reads = 0

    def unavailable_sources(self: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal compose_reads
        if self == compose_path:
            compose_reads += 1
            if compose_reads == 1:
                return original_read_text(self, *args, **kwargs)
            raise OSError("compose unavailable")
        if self.name == "Dockerfile":
            raise OSError("dockerfile unavailable")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unavailable_sources)

    assert _findings(_valid_document(), tmp_path)[1] == [
        _finding(
            "runtime_source_unreadable",
            "manifest.images.python_base",
            "Không thể đọc runtime source để đối chiếu version.",
        ),
        _finding(
            "runtime_source_unreadable",
            "manifest.images.node_base",
            "Không thể đọc runtime source để đối chiếu version.",
        ),
        _finding(
            "runtime_source_unreadable",
            "manifest.images.postgresql",
            "Không thể đọc runtime source để đối chiếu version.",
        ),
        _finding(
            "runtime_source_unreadable",
            "manifest.images.qdrant",
            "Không thể đọc runtime source để đối chiếu version.",
        ),
    ]
    assert compose_reads == 3


def test_runtime_source_unicode_decode_error_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    python_dockerfile = tmp_path / "Dockerfile"
    original_read_text = Path.read_text
    findings: list[Finding] = []

    def invalid_utf8(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == python_dockerfile:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", invalid_utf8)

    with pytest.raises(UnicodeDecodeError):
        _validate_repository_contract(_valid_document(), tmp_path, findings)
    assert findings == []


@pytest.mark.parametrize("failure", ["os_error", "unicode", "json"])
def test_unreadable_or_malformed_frontend_package_is_one_terminal_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    _write_repository(tmp_path)
    package_path = tmp_path / "frontend" / "package.json"
    original_read_text = Path.read_text
    document = _valid_document()
    document["versions"]["frontend"] = "wrong"
    document["versions"]["nextjs"] = "wrong"

    def broken_package(self: Path, *args: Any, **kwargs: Any) -> str:
        if self != package_path:
            return original_read_text(self, *args, **kwargs)
        if failure == "os_error":
            raise OSError("unavailable")
        if failure == "unicode":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        return "{not-json"

    monkeypatch.setattr(Path, "read_text", broken_package)

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "frontend_package_unreadable",
            "manifest.versions.frontend",
            "Không thể đọc frontend package metadata để đối chiếu version.",
        )
    ]
