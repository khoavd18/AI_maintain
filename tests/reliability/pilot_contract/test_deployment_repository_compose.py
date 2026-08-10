"""Repository-binding tests grouped by checked-in surface."""

from __future__ import annotations

from ._repository_contract_scenarios import (
    Any,
    COMPOSE_NAME,
    Finding,
    POSTGRES_IMAGE,
    Path,
    QDRANT_IMAGE,
    _finding,
    _findings,
    _repository_bytes,
    _valid_document,
    _validate_repository_contract,
    _write_repository,
    deepcopy,
    manifest_repository_contract_validator,
    pytest,
    signature,
)


def test_valid_repository_contract_is_deterministic_and_read_only(tmp_path: Path) -> None:
    before_files = _write_repository(tmp_path)
    document = _valid_document()
    before_document = deepcopy(document)

    first_result, first = _findings(document, tmp_path)
    second_result, second = _findings(document, tmp_path)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert document == before_document
    assert _repository_bytes(tmp_path) == before_files
    assert list(signature(_validate_repository_contract).parameters) == [
        "document",
        "repository_root",
        "findings",
    ]
    assert manifest_repository_contract_validator is _validate_repository_contract


@pytest.mark.parametrize(
    "compose_file",
    [
        None,
        "",
        " ",
        "..",
        "../compose.yml",
        "/compose.yml",
        "//server/compose.yml",
        "C:/compose.yml",
        "C:\\compose.yml",
        "https://example.invalid/compose.yml",
        "compose\x00.yml",
    ],
)
def test_invalid_compose_paths_short_circuit_all_other_checks(
    tmp_path: Path,
    compose_file: object,
) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["compose_file"] = compose_file
    document["versions"] = {}
    document["release"] = {}
    document["images"] = {}

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "invalid_compose_file",
            "manifest.compose_file",
            "Compose file phải là đường dẫn tương đối nằm trong repository.",
        )
    ]


@pytest.mark.parametrize("compose_file", ["missing.yml", ".", "frontend"])
def test_missing_or_non_file_compose_short_circuits_all_other_checks(
    tmp_path: Path,
    compose_file: str,
) -> None:
    _write_repository(tmp_path)
    document = _valid_document()
    document["compose_file"] = compose_file
    document["versions"] = {}

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "compose_file_missing",
            "manifest.compose_file",
            "Không tìm thấy Compose file đã khai báo.",
        )
    ]


def test_resolved_compose_escape_uses_missing_finding_and_short_circuits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    compose_path = tmp_path / COMPOSE_NAME
    outside_path = tmp_path.parent / "outside-compose.yml"
    original_resolve = Path.resolve

    def escaping_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self == compose_path:
            return outside_path
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escaping_resolve)

    assert _findings(_valid_document(), tmp_path)[1] == [
        _finding(
            "compose_file_missing",
            "manifest.compose_file",
            "Không tìm thấy Compose file đã khai báo.",
        )
    ]


def test_compose_os_error_is_a_finding_and_short_circuits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    compose_path = tmp_path / COMPOSE_NAME
    original_read_text = Path.read_text
    reads: list[str] = []

    def unreadable(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self.relative_to(tmp_path).as_posix())
        if self == compose_path:
            raise OSError("denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)

    assert _findings(_valid_document(), tmp_path)[1] == [
        _finding(
            "compose_file_unreadable",
            "manifest.compose_file",
            "Không thể đọc Compose file đã khai báo.",
        )
    ]
    assert reads == [COMPOSE_NAME]


def test_compose_unicode_decode_error_propagates_without_a_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_repository(tmp_path)
    compose_path = tmp_path / COMPOSE_NAME
    original_read_text = Path.read_text
    findings: list[Finding] = []

    def invalid_utf8(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == compose_path:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", invalid_utf8)

    with pytest.raises(UnicodeDecodeError):
        _validate_repository_contract(_valid_document(), tmp_path, findings)
    assert findings == []


def test_compose_environment_discovery_is_sorted_exact_and_deduplicated(
    tmp_path: Path,
) -> None:
    _write_repository(
        tmp_path,
        compose_text=(
            "services:\n"
            f"  postgres:\n    image: {POSTGRES_IMAGE}\n"
            f"  qdrant:\n    image: {QDRANT_IMAGE}\n"
            "  api:\n    environment:\n"
            "      A: ${ZED_ENV:?required}\n"
            "      B: ${ALPHA_ENV:?required}\n"
            "      C: ${ZED_ENV:?again}\n"
            "      D: ${IGNORED_ENV}\n"
            "      E: ${DEFAULT_ENV:-value}\n"
            "      F: ${lower_env:?required}\n"
        ),
    )
    document = _valid_document()
    document["required_environment_variables"] = [
        42,
        {"name": "ALPHA_ENV", "secret": False},
        {"name": "ALPHA_ENV", "secret": True},
        {"name": " zed_env ", "secret": False},
        {"name": 1, "secret": False},
    ]

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "compose_environment_not_declared",
            "manifest.required_environment_variables.ZED_ENV",
            "Biến bắt buộc của Compose chưa có trong manifest: ZED_ENV.",
        )
    ]


def test_missing_compose_environment_findings_are_sorted(tmp_path: Path) -> None:
    _write_repository(
        tmp_path,
        compose_text=(
            "services:\n"
            f"  postgres:\n    image: {POSTGRES_IMAGE}\n"
            f"  qdrant:\n    image: {QDRANT_IMAGE}\n"
            "  api:\n    environment:\n"
            "      Z: ${ZED_ENV:?required}\n"
            "      A: ${ALPHA_ENV:?required}\n"
        ),
    )
    document = _valid_document()
    document["required_environment_variables"] = None

    assert _findings(document, tmp_path)[1] == [
        _finding(
            "compose_environment_not_declared",
            "manifest.required_environment_variables.ALPHA_ENV",
            "Biến bắt buộc của Compose chưa có trong manifest: ALPHA_ENV.",
        ),
        _finding(
            "compose_environment_not_declared",
            "manifest.required_environment_variables.ZED_ENV",
            "Biến bắt buộc của Compose chưa có trong manifest: ZED_ENV.",
        ),
    ]
