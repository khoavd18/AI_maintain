"""Safe, infrastructure-free tests for the PM9 deployment rehearsal."""

from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from src.reliability.deployment_rehearsal import (
    DeploymentRehearsalError,
    _bound_endpoint,
    _probe_payload_matches,
    _validate_migration_revision,
    cleanup_deployment_rehearsal,
    compose_command,
    load_environment_file,
    main as deployment_main,
    run_deployment_rehearsal,
)
from src.reliability.post_start_validation import PostStartValidationError

DESIGN_READINESS_TAG = "product-milestone-9-pilot-ready-by-design"


def _environment(*, approved: bool = False) -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[1]
    values = load_environment_file(repository_root / ".env.pilot.example")
    values.update(
        {
            "RELEASE_IDENTIFIER": "product-milestone-9",
            "RELEASE_GIT_COMMIT": "a" * 40,
            "RELEASE_GIT_TAG": DESIGN_READINESS_TAG,
            "RELEASE_ALEMBIC_REVISION": "20260726_0008",
            "PILOT_HOST_IDENTIFIER": "synthetic-pilot-host",
            "PILOT_HOST_APPROVED": str(approved).lower(),
            "DATABASE_URL": (
                "postgresql+psycopg://pilot_user:"
                "synthetic-password-value@postgres:5432/pilot_database"
            ),
            "POSTGRES_USER": "pilot_user",
            "POSTGRES_PASSWORD": "synthetic-password-value",
            "POSTGRES_DB": "pilot_database",
            "TOKEN_SIGNING_SECRET": "synthetic-signing-value-" + ("s" * 32),
            "AUTH_COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "https://pilot.example.test",
            "TRUSTED_HOSTS": "pilot-api.example.test",
            "FRONTEND_BASE_URL": "https://pilot.example.test",
            "NEXT_PUBLIC_API_BASE_URL": "https://pilot-api.example.test",
            "PILOT_ALLOWED_DATA_ROOT": str(
                (repository_root.parent / "pm9-rehearsal-data").resolve()
            ),
            "PILOT_BACKUP_ROOT": str((repository_root.parent / "pm9-rehearsal-backups").resolve()),
        }
    )
    return values


def _write_environment(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()),
        encoding="utf-8",
    )


def _enable_authenticated_post_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    monkeypatch.setenv("PM9_APPROVED_DATA_ATTESTED", "true")
    monkeypatch.setenv("PM9_APPROVED_DATA_EVIDENCE_ID", "approved-data-20260726")
    monkeypatch.setenv("PM9_SMOKE_OPERATOR_USERNAME", "synthetic-operator")
    monkeypatch.setenv(
        "PM9_SMOKE_OPERATOR_PASSWORD",
        "synthetic-operator-password",
    )
    monkeypatch.setenv("PM9_SMOKE_RESTRICTED_USERNAME", "synthetic-restricted")
    monkeypatch.setenv(
        "PM9_SMOKE_RESTRICTED_PASSWORD",
        "synthetic-restricted-password",
    )


def _passed_post_start_report() -> SimpleNamespace:
    checks = tuple(
        SimpleNamespace(name=name, status="passed")
        for name in (
            "unauthenticated_boundary",
            "release_and_readiness",
            "operator_authentication",
            "operator_session_refresh",
            "restricted_authentication",
            "rbac_boundary",
            "scheduled_jobs",
            "approved_data_reads",
            "analytics_availability",
            "notification_owner_isolation",
            "session_cleanup",
        )
    )
    return SimpleNamespace(overall_status="passed", checks=checks)


def _git_runner(
    command,
    **_kwargs,
) -> subprocess.CompletedProcess[str]:
    if tuple(command[:3]) == ("git", "rev-parse", "HEAD"):
        return subprocess.CompletedProcess(command, 0, stdout=("a" * 40) + "\n")
    if tuple(command[:3]) == ("git", "describe", "--tags"):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"{DESIGN_READINESS_TAG}\n",
        )
    raise AssertionError("Plan mode must not execute Compose.")


def test_environment_parser_does_not_expand_values_and_rejects_duplicates(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / "pilot.env"
    environment_file.write_text(
        "TOKEN_SIGNING_SECRET='$DO_NOT_EXPAND'\nAPP_ENVIRONMENT=pilot\n",
        encoding="utf-8",
    )
    values = load_environment_file(environment_file)
    assert values["TOKEN_SIGNING_SECRET"] == "$DO_NOT_EXPAND"

    environment_file.write_text(
        "APP_ENVIRONMENT=pilot\nAPP_ENVIRONMENT=production\n",
        encoding="utf-8",
    )
    with pytest.raises(DeploymentRehearsalError, match="more than once"):
        load_environment_file(environment_file)


def test_compose_surface_is_closed_and_uses_dedicated_project(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / "pilot.env"
    command = compose_command(
        project_name="pm9-rehearsal",
        environment_file=environment_file,
        operation=("config", "--quiet"),
    )
    assert command[:3] == ("docker", "compose", "--project-name")
    collision_check = compose_command(
        project_name="pm9-rehearsal",
        environment_file=environment_file,
        operation=("ps", "--all", "--services"),
    )
    assert collision_check[-3:] == ("ps", "--all", "--services")
    with pytest.raises(ValueError, match="Unsupported"):
        compose_command(
            project_name="pm9-rehearsal",
            environment_file=environment_file,
            operation=("down", "--volumes"),
        )
    with pytest.raises(ValueError, match=r"pm9-\*"):
        compose_command(
            project_name="developer-stack",
            environment_file=environment_file,
            operation=("config", "--quiet"),
        )


def test_plan_is_non_mutating_and_keeps_unverified_contract_no_go(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment()
    secret = values["TOKEN_SIGNING_SECRET"]
    _write_environment(environment_file, values)

    report, evidence_path = run_deployment_rehearsal(
        environment_file=environment_file,
        execute=False,
        runner=_git_runner,
    )

    assert report.executed is False
    assert report.overall_status == "not_executed"
    assert report.contract_decision == "NO-GO / NOT YET VERIFIED"
    assert report.host_identifier == "synthetic-pilot-host"
    assert evidence_path is None
    assert secret not in str(report.as_dict())
    assert all(step.status == "not_executed" for step in report.steps)


def test_rehearsal_rejects_missing_placeholder_or_unbounded_host_identifier(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment()
    for invalid in (
        "",
        "REPLACE_WITH_APPROVED_OPAQUE_HOST_ID",
        "host identifier with spaces",
        "h" * 129,
    ):
        values["PILOT_HOST_IDENTIFIER"] = invalid
        _write_environment(environment_file, values)
        with pytest.raises(
            DeploymentRehearsalError,
            match="PILOT_HOST_IDENTIFIER|missing required",
        ):
            run_deployment_rehearsal(
                environment_file=environment_file,
                execute=False,
                runner=_git_runner,
            )


def test_execute_requires_explicit_host_approval_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=False))
    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")

    with pytest.raises(DeploymentRehearsalError, match="PILOT_HOST_APPROVED"):
        run_deployment_rehearsal(
            environment_file=environment_file,
            evidence_dir=tmp_path / "evidence",
            execute=True,
            runner=_git_runner,
        )


def test_execute_requires_an_exact_release_tag_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    calls: list[tuple[str, ...]] = []

    def untagged_runner(command, **_kwargs):
        selected = tuple(command)
        calls.append(selected)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            raise subprocess.CalledProcessError(128, command)
        raise AssertionError("Compose must not run for an untagged release.")

    with pytest.raises(DeploymentRehearsalError, match="Git release identity"):
        run_deployment_rehearsal(
            environment_file=environment_file,
            evidence_dir=tmp_path / "evidence",
            execute=True,
            runner=untagged_runner,
        )

    assert all(call[0] == "git" for call in calls)


def test_execute_rejects_dirty_release_content_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    calls: list[tuple[str, ...]] = []

    def dirty_runner(command, **_kwargs):
        selected = tuple(command)
        calls.append(selected)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        if selected[:2] == ("git", "status"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="1 .M N... src/api/main.py\n",
                stderr="",
            )
        raise AssertionError("Compose must not run from dirty release content.")

    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    with pytest.raises(DeploymentRehearsalError, match="clean release worktree"):
        run_deployment_rehearsal(
            environment_file=environment_file,
            evidence_dir=tmp_path.parent / f"{tmp_path.name}-evidence",
            execute=True,
            runner=dirty_runner,
        )

    assert calls[-1][:2] == ("git", "status")
    assert all(call[0] == "git" for call in calls)


def test_health_probe_requires_release_identity_when_requested() -> None:
    payload = {
        "status": "ready",
        "release": {"identifier": "product-milestone-9"},
    }
    assert _probe_payload_matches(
        payload,
        expected_status="ready",
        expected_release="product-milestone-9",
    )
    assert not _probe_payload_matches(
        payload,
        expected_status="ready",
        expected_release="different-release",
    )
    assert _probe_payload_matches(
        None,
        expected_status=None,
        expected_release=None,
    )


def test_bound_probe_uses_loopback_for_wildcard_listener() -> None:
    environment = {
        "PILOT_API_BIND_ADDRESS": "0.0.0.0",
        "PILOT_API_PORT": "8000",
    }

    assert (
        _bound_endpoint(
            environment,
            "PILOT_API_BIND_ADDRESS",
            "PILOT_API_PORT",
            "/health/live",
        )
        == "http://127.0.0.1:8000/health/live"
    )


def test_cleanup_only_removes_project_without_removing_volumes(tmp_path: Path) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment())
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    status = cleanup_deployment_rehearsal(
        environment_file=environment_file,
        project_name="pm9-rehearsal",
        runner=runner,
    )

    assert status == "completed"
    assert len(calls) == 1
    assert "down" in calls[0]
    assert "--remove-orphans" in calls[0]
    assert "--volumes" not in calls[0]


def test_existing_project_collision_is_refused_without_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    evidence_dir = tmp_path.parent / f"{tmp_path.name}-evidence"
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        if selected[:2] == ("git", "status"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        calls.append(selected)
        if "config" in selected:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "ps" in selected and "--all" in selected:
            return subprocess.CompletedProcess(command, 0, stdout="api\n", stderr="")
        raise AssertionError("Collision refusal must precede build and cleanup.")

    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    report, report_path = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=evidence_dir,
        execute=True,
        runner=runner,
    )

    by_name = {step.name: step for step in report.steps}
    assert report.overall_status == "failed"
    assert report.cleanup_status == "not_required"
    assert by_name["validate_project_absent"].status == "failed"
    assert report_path is not None
    assert not any("down" in call for call in calls)


def test_leave_running_still_cleans_up_after_partial_startup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    evidence_dir = tmp_path.parent / f"{tmp_path.name}-evidence"
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        calls.append(selected)
        if "build" in selected:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    report, report_path = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=evidence_dir,
        execute=True,
        leave_running=True,
        runner=runner,
    )

    assert report.overall_status == "failed"
    assert report.cleanup_status == "completed"
    assert report_path is not None
    assert any("build" in call for call in calls)
    cleanup = calls[-1]
    assert "down" in cleanup
    assert "--remove-orphans" in cleanup
    assert "--volumes" not in cleanup


def test_leave_running_does_not_strand_stack_when_post_start_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment(approved=True)
    _write_environment(environment_file, values)
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        if selected[:2] == ("git", "status"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        calls.append(selected)
        stdout = values["RELEASE_ALEMBIC_REVISION"] + " (head)\n" if "current" in selected else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def probe(url: str):
        if url.endswith("/health/live"):
            return (
                True,
                {
                    "status": "alive",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        if url.endswith("/health/ready"):
            return (
                True,
                {
                    "status": "ready",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        return True, None

    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    report, _ = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=tmp_path.parent / f"{tmp_path.name}-evidence",
        execute=True,
        leave_running=True,
        runner=runner,
        probe=probe,
    )

    assert report.overall_status == "failed"
    assert report.cleanup_status == "completed"
    assert "down" in calls[-1]


def test_authenticated_post_start_requires_data_attestation_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    monkeypatch.setenv("PM9_ALLOW_DEPLOYMENT_REHEARSAL", "true")
    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    with pytest.raises(
        DeploymentRehearsalError,
        match="PM9_APPROVED_DATA_ATTESTED",
    ):
        run_deployment_rehearsal(
            environment_file=environment_file,
            evidence_dir=tmp_path.parent / f"{tmp_path.name}-evidence",
            execute=True,
            authenticated_post_start=True,
            runner=_git_runner,
        )


def test_authenticated_post_start_execution_guard_is_checked_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    _write_environment(environment_file, _environment(approved=True))
    _enable_authenticated_post_start(monkeypatch)
    monkeypatch.delenv("PM9_ALLOW_POST_START_VALIDATION")
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        calls.append(selected)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        raise AssertionError("Post-start preflight must precede Compose.")

    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )

    with pytest.raises(
        DeploymentRehearsalError,
        match="PM9_ALLOW_POST_START_VALIDATION",
    ):
        run_deployment_rehearsal(
            environment_file=environment_file,
            evidence_dir=tmp_path.parent / f"{tmp_path.name}-evidence",
            execute=True,
            authenticated_post_start=True,
            runner=runner,
        )

    assert all(call[0] == "git" for call in calls)


def test_authenticated_post_start_can_complete_the_closed_deployment_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment(approved=True)
    _write_environment(environment_file, values)
    evidence_dir = tmp_path.parent / f"{tmp_path.name}-evidence"
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        calls.append(selected)
        stdout = values["RELEASE_ALEMBIC_REVISION"] + " (head)\n" if "current" in selected else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def probe(url: str):
        if url.endswith("/health/live"):
            return (
                True,
                {
                    "status": "alive",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        if url.endswith("/health/ready"):
            return (
                True,
                {
                    "status": "ready",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        return True, None

    _enable_authenticated_post_start(monkeypatch)
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal._run_authenticated_post_start",
        lambda **_kwargs: _passed_post_start_report(),
    )

    report, report_path = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=evidence_dir,
        execute=True,
        authenticated_post_start=True,
        runner=runner,
        probe=probe,
    )

    assert report.overall_status == "passed"
    assert report.cleanup_status == "completed"
    assert report.approved_data_evidence_id == "approved-data-20260726"
    assert report_path is not None
    mapped = {
        step.name: step
        for step in report.steps
        if step.name
        in {
            "prepare_approved_data",
            "authenticated_rbac_smoke",
            "scheduled_job_validation",
            "notification_validation",
            "analytics_validation",
        }
    }
    assert set(mapped) == {
        "prepare_approved_data",
        "authenticated_rbac_smoke",
        "scheduled_job_validation",
        "notification_validation",
        "analytics_validation",
    }
    assert all(step.status == "passed" for step in mapped.values())
    assert "down" in calls[-1]
    assert "--volumes" not in calls[-1]


def test_post_start_runtime_preflight_failure_is_wrapped_and_cleaned_when_left_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment(approved=True)
    _write_environment(environment_file, values)
    evidence_dir = tmp_path.parent / f"{tmp_path.name}-evidence"
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        if selected[:2] == ("git", "status"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        calls.append(selected)
        stdout = values["RELEASE_ALEMBIC_REVISION"] + " (head)\n" if "current" in selected else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def probe(url: str):
        if url.endswith("/health/live"):
            return (
                True,
                {
                    "status": "alive",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        if url.endswith("/health/ready"):
            return (
                True,
                {
                    "status": "ready",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        return True, None

    def fail_post_start(**_kwargs):
        raise PostStartValidationError("safe post-start preflight failure")

    _enable_authenticated_post_start(monkeypatch)
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )
    monkeypatch.setattr(
        "src.reliability.post_start_validation.run_post_start_validation",
        fail_post_start,
    )

    report, report_path = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=evidence_dir,
        execute=True,
        leave_running=True,
        authenticated_post_start=True,
        runner=runner,
        probe=probe,
    )

    assert report.overall_status == "failed"
    assert report.cleanup_status == "completed"
    assert report_path is not None
    assert "down" in calls[-1]


def test_successful_validation_with_failed_cleanup_is_failed_and_cli_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_file = tmp_path / "pilot.env"
    values = _environment(approved=True)
    _write_environment(environment_file, values)
    evidence_dir = tmp_path.parent / f"{tmp_path.name}-evidence"

    def runner(command, **_kwargs):
        selected = tuple(command)
        if selected[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=("a" * 40) + "\n",
            )
        if selected[:3] == ("git", "describe", "--tags"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{DESIGN_READINESS_TAG}\n",
            )
        if selected[:2] == ("git", "status"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "down" in selected:
            raise subprocess.CalledProcessError(1, command)
        stdout = values["RELEASE_ALEMBIC_REVISION"] + " (head)\n" if "current" in selected else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def probe(url: str):
        if url.endswith("/health/live"):
            return (
                True,
                {
                    "status": "alive",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        if url.endswith("/health/ready"):
            return (
                True,
                {
                    "status": "ready",
                    "release": {"identifier": values["RELEASE_IDENTIFIER"]},
                },
            )
        return True, None

    _enable_authenticated_post_start(monkeypatch)
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.validate_deployment_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_valid=True,
            manifest_sha256="f" * 64,
            decision="NO-GO / NOT YET VERIFIED",
        ),
    )
    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal._run_authenticated_post_start",
        lambda **_kwargs: _passed_post_start_report(),
    )

    report, report_path = run_deployment_rehearsal(
        environment_file=environment_file,
        evidence_dir=evidence_dir,
        execute=True,
        authenticated_post_start=True,
        runner=runner,
        probe=probe,
    )

    assert report.overall_status == "failed"
    assert report.cleanup_status == "failed"
    assert report_path is not None

    monkeypatch.setattr(
        "src.reliability.deployment_rehearsal.run_deployment_rehearsal",
        lambda **_kwargs: (report, report_path),
    )
    assert (
        deployment_main(
            [
                "--environment-file",
                str(environment_file),
                "--execute",
            ]
        )
        == 2
    )


def test_migration_revision_rejects_multiple_observed_heads(tmp_path: Path) -> None:
    environment_file = tmp_path / "pilot.env"
    environment_file.write_text("APP_ENVIRONMENT=pilot\n", encoding="utf-8")
    steps = []

    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="20260726_0008 (head)\n20260726_other (head)\n",
            stderr="",
        )

    with pytest.raises(DeploymentRehearsalError, match="does not match"):
        _validate_migration_revision(
            expected_revision="20260726_0008",
            project_name="pm9-rehearsal",
            environment_file=environment_file,
            environment={},
            runner=runner,
            steps=steps,
        )

    assert steps[-1].status == "failed"
