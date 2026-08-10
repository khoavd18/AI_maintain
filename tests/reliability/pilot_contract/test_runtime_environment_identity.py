"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_environment,
    pytest,
)


def test_release_and_image_environment_mismatches_keep_mapping_order() -> None:
    environment = _ready_environment()
    for name in (
        "RELEASE_IDENTIFIER",
        "RELEASE_GIT_TAG",
        "RELEASE_ALEMBIC_REVISION",
        "PILOT_APP_IMAGE",
        "PILOT_FRONTEND_IMAGE",
    ):
        environment[name] = "wrong"

    assert _only(
        _findings(environment=environment)[1],
        {"release_environment_mismatch", "image_environment_mismatch"},
    ) == [
        *[
            _finding(
                "release_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp release manifest.",
            )
            for name in (
                "RELEASE_IDENTIFIER",
                "RELEASE_GIT_TAG",
                "RELEASE_ALEMBIC_REVISION",
            )
        ],
        *[
            _finding(
                "image_environment_mismatch",
                f"environment.{name}",
                f"{name} không khớp image reference trong manifest.",
            )
            for name in ("PILOT_APP_IMAGE", "PILOT_FRONTEND_IMAGE")
        ],
    ]


@pytest.mark.parametrize("commit", ["a" * 39, "g" * 40, " " + "a" * 40, "abc"])
def test_release_commit_requires_exact_full_hex_sha(commit: str) -> None:
    environment = _ready_environment()
    environment["RELEASE_GIT_COMMIT"] = commit

    assert _only(_findings(environment=environment)[1], {"release_environment_commit_invalid"}) == [
        _finding(
            "release_environment_commit_invalid",
            "environment.RELEASE_GIT_COMMIT",
            "RELEASE_GIT_COMMIT phải là full 40-character Git SHA.",
        )
    ]


def test_missing_optional_runtime_identity_values_do_not_mismatch() -> None:
    environment = _ready_environment()
    for name in (
        "RELEASE_IDENTIFIER",
        "RELEASE_GIT_TAG",
        "RELEASE_ALEMBIC_REVISION",
        "RELEASE_GIT_COMMIT",
        "PILOT_APP_IMAGE",
        "PILOT_FRONTEND_IMAGE",
    ):
        environment[name] = ""

    assert not {
        "release_environment_mismatch",
        "release_environment_commit_invalid",
        "image_environment_mismatch",
    } & {finding.code for finding in _findings(environment=environment)[1]}
