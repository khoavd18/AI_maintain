"""Fail-fast, bounded Docker Compose rehearsal for an approved pilot host.

The command surface is intentionally closed. It cannot accept arbitrary shell,
SQL, Python, or workflow definitions. Secret values are read from an ignored
environment file, passed only through the child-process environment, and never
included in evidence.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Literal
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.reliability.environment_loader import (
    EnvironmentFileError,
    load_environment_file as _load_environment_file,
)
from src.reliability.pilot_contract import (
    ValidationReport,
    validate_deployment_manifest,
)

_EXECUTION_FLAG = "PM9_ALLOW_DEPLOYMENT_REHEARSAL"
_POST_START_EXECUTION_FLAG = "PM9_ALLOW_POST_START_VALIDATION"
_HOST_APPROVAL_FLAG = "PILOT_HOST_APPROVED"
_EMPTY_DATA_FLAG = "PM9_ALLOW_EMPTY_TEST_DATA"
_APPROVED_DATA_FLAG = "PM9_APPROVED_DATA_ATTESTED"
_APPROVED_DATA_EVIDENCE_ENV = "PM9_APPROVED_DATA_EVIDENCE_ID"
_SMOKE_CREDENTIAL_ENVIRONMENTS = (
    "PM9_SMOKE_OPERATOR_USERNAME",
    "PM9_SMOKE_OPERATOR_PASSWORD",
    "PM9_SMOKE_RESTRICTED_USERNAME",
    "PM9_SMOKE_RESTRICTED_PASSWORD",
)
_PROJECT_PATTERN = re.compile(r"^pm9-[a-z0-9][a-z0-9-]{0,39}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EVIDENCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,99}$")
_HOST_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,127}$")
_PLACEHOLDER_MARKERS = ("REPLACE_WITH", "PLACEHOLDER", "UNSET", "UNVERIFIED")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _REPOSITORY_ROOT / "docker-compose.pilot.yml"

DataMode = Literal["existing_approved", "empty_test"]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Probe = Callable[[str], tuple[bool, dict[str, Any] | None]]


class DeploymentRehearsalError(RuntimeError):
    """Safe operator-facing rehearsal failure."""


@dataclass(frozen=True, slots=True)
class RehearsalStep:
    name: str
    status: Literal["passed", "failed", "not_executed"]
    duration_ms: int | None
    evidence_code: str


@dataclass(frozen=True, slots=True)
class RehearsalReport:
    """Redacted summary suitable for an outside-repository evidence directory."""

    schema_version: int
    generated_at: str
    scope: str
    executed: bool
    host_approved: bool
    host_identifier: str
    intended_host_claim: bool
    production_readiness_claim: bool
    release_identifier: str
    release_commit: str
    release_tag: str
    alembic_revision: str
    data_mode: DataMode
    approved_data_evidence_id: str | None
    manifest_sha256: str
    contract_decision: str
    overall_status: Literal["passed", "failed", "not_executed"]
    cleanup_status: Literal["completed", "failed", "not_required", "not_executed"]
    steps: tuple[RehearsalStep, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["steps"] = [asdict(step) for step in self.steps]
        return value


def load_environment_file(path: Path) -> dict[str, str]:
    """Compatibility wrapper preserving the rehearsal exception type."""

    try:
        return _load_environment_file(path)
    except EnvironmentFileError as exc:
        raise DeploymentRehearsalError(str(exc)) from None


def compose_command(
    *,
    project_name: str,
    environment_file: Path,
    operation: Sequence[str],
) -> tuple[str, ...]:
    """Build one fixed Compose argument vector."""

    if not _PROJECT_PATTERN.fullmatch(project_name):
        raise ValueError("Compose project name must use the dedicated pm9-* namespace.")
    allowed_operations = {
        ("config", "--quiet"),
        ("build", "--pull=false", "migrate", "api", "worker", "frontend"),
        ("up", "-d", "postgres", "qdrant"),
        ("up", "-d", "migrate"),
        ("wait", "migrate"),
        (
            "run",
            "--rm",
            "--no-deps",
            "migrate",
            "python",
            "-m",
            "alembic",
            "current",
        ),
        ("up", "-d", "api", "worker", "frontend"),
        ("ps", "--all", "--services"),
        ("ps", "--status", "running", "--services"),
        ("down", "--remove-orphans"),
    }
    selected = tuple(operation)
    if selected not in allowed_operations:
        raise ValueError("Unsupported pilot Compose operation.")
    return (
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--env-file",
        str(environment_file.resolve()),
        "--file",
        str(_COMPOSE_FILE),
        *selected,
    )


def run_deployment_rehearsal(
    *,
    environment_file: Path,
    manifest_path: Path = _REPOSITORY_ROOT / "deployment" / "pilot_manifest.json",
    project_name: str = "pm9-pilot-rehearsal",
    data_mode: DataMode = "existing_approved",
    evidence_dir: Path | None = None,
    execute: bool = False,
    leave_running: bool = False,
    intended_host: bool = False,
    authenticated_post_start: bool = False,
    runner: CommandRunner = subprocess.run,
    probe: Probe | None = None,
) -> tuple[RehearsalReport, Path | None]:
    """Plan or execute the closed full-stack rehearsal sequence."""

    environment = load_environment_file(environment_file)
    _validate_release_environment(environment)
    _validate_data_mode(data_mode, environment)
    actual_commit = _git_output(("git", "rev-parse", "HEAD"), runner=runner)
    actual_tag = _git_output(
        ("git", "describe", "--tags", "--exact-match", "HEAD"),
        runner=runner,
        required=execute,
    )
    contract = validate_deployment_manifest(
        manifest_path,
        environment=environment,
        actual_commit=actual_commit,
        actual_tag=actual_tag,
        repository_root=_REPOSITORY_ROOT,
    )
    host_approved = _truthy(environment.get(_HOST_APPROVAL_FLAG))

    if not execute:
        report = _planned_report(
            environment=environment,
            data_mode=data_mode,
            contract=contract,
            host_approved=host_approved,
            intended_host=intended_host,
        )
        return report, None

    if os.getenv(_EXECUTION_FLAG) != "true":
        raise DeploymentRehearsalError(f"Execution requires {_EXECUTION_FLAG}=true.")
    if not host_approved:
        raise DeploymentRehearsalError(
            f"Execution requires {_HOST_APPROVAL_FLAG}=true in the pilot environment."
        )
    if not contract.is_valid:
        raise DeploymentRehearsalError(
            "Deployment contract has blocking findings; execution was refused."
        )
    if authenticated_post_start:
        _validate_authenticated_post_start_inputs(
            environment=environment,
            manifest_path=manifest_path,
            intended_host=intended_host,
        )
    _validate_clean_release_worktree(runner=runner)
    output_root = _validated_evidence_dir(evidence_dir)
    child_environment = os.environ.copy()
    child_environment.update(environment)
    active_probe = probe or _http_probe
    steps: list[RehearsalStep] = []
    cleanup_status: Literal["completed", "failed", "not_required"] = "not_required"
    execution_failed = False
    sequence_completed = False
    project_claimed = False
    steps.append(
        RehearsalStep(
            name="validate_release_inputs",
            status="passed",
            duration_ms=None,
            evidence_code="manifest_and_git_identity_validated",
        )
    )

    startup_operations = (
        (
            "build_release_images",
            ("build", "--pull=false", "migrate", "api", "worker", "frontend"),
        ),
        ("start_dependencies", ("up", "-d", "postgres", "qdrant")),
        ("start_alembic_migration", ("up", "-d", "migrate")),
        ("apply_alembic_migrations", ("wait", "migrate")),
    )
    try:
        _run_step(
            name="validate_compose",
            operation=("config", "--quiet"),
            project_name=project_name,
            environment_file=environment_file,
            environment=child_environment,
            runner=runner,
            steps=steps,
        )
        _validate_project_absent(
            project_name=project_name,
            environment_file=environment_file,
            environment=child_environment,
            runner=runner,
            steps=steps,
        )
        # From this point forward the rehearsal may create project-scoped state,
        # so only this invocation is allowed to clean the dedicated project.
        project_claimed = True
        for name, operation in startup_operations:
            _run_step(
                name=name,
                operation=operation,
                project_name=project_name,
                environment_file=environment_file,
                environment=child_environment,
                runner=runner,
                steps=steps,
            )
        _validate_migration_revision(
            expected_revision=environment["RELEASE_ALEMBIC_REVISION"],
            project_name=project_name,
            environment_file=environment_file,
            environment=child_environment,
            runner=runner,
            steps=steps,
        )
        for name, operation in (
            ("start_application", ("up", "-d", "api", "worker", "frontend")),
            (
                "validate_running_services",
                ("ps", "--status", "running", "--services"),
            ),
        ):
            _run_step(
                name=name,
                operation=operation,
                project_name=project_name,
                environment_file=environment_file,
                environment=child_environment,
                runner=runner,
                steps=steps,
            )
        _probe_step(
            name="api_liveness",
            url=_bound_endpoint(
                environment,
                "PILOT_API_BIND_ADDRESS",
                "PILOT_API_PORT",
                "/health/live",
            ),
            expected_status="alive",
            expected_release=environment["RELEASE_IDENTIFIER"],
            probe=active_probe,
            steps=steps,
        )
        _probe_step(
            name="api_readiness",
            url=_bound_endpoint(
                environment,
                "PILOT_API_BIND_ADDRESS",
                "PILOT_API_PORT",
                "/health/ready",
            ),
            expected_status="ready",
            expected_release=environment["RELEASE_IDENTIFIER"],
            probe=active_probe,
            steps=steps,
        )
        _probe_step(
            name="worker_readiness",
            url=_bound_endpoint(
                environment,
                "PILOT_API_BIND_ADDRESS",
                "PILOT_API_PORT",
                "/health/worker",
            ),
            expected_status=None,
            expected_release=None,
            probe=active_probe,
            steps=steps,
        )
        _probe_step(
            name="qdrant_readiness",
            url=_bound_endpoint(
                environment,
                "PILOT_QDRANT_BIND_ADDRESS",
                "PILOT_QDRANT_PORT",
                "/readyz",
            ),
            expected_status=None,
            expected_release=None,
            probe=active_probe,
            steps=steps,
        )
        _probe_step(
            name="frontend_availability",
            url=_bound_endpoint(
                environment,
                "PILOT_FRONTEND_BIND_ADDRESS",
                "PILOT_FRONTEND_PORT",
                "/",
            ),
            expected_status=None,
            expected_release=None,
            probe=active_probe,
            steps=steps,
        )
        if authenticated_post_start:
            post_start_report = _run_authenticated_post_start(
                environment=environment,
                manifest_path=manifest_path,
                evidence_dir=output_root,
                intended_host=intended_host,
            )
            _append_post_start_steps(post_start_report, steps=steps)
            sequence_completed = True
    except (DeploymentRehearsalError, OSError, subprocess.SubprocessError):
        execution_failed = True
        if not steps or steps[-1].status != "failed":
            steps.append(
                RehearsalStep(
                    name="rehearsal",
                    status="failed",
                    duration_ms=None,
                    evidence_code="safe_failure",
                )
            )
    finally:
        # ``--leave-running`` is only meaningful after every required automated
        # check succeeds. A failure, omitted post-start gate, or unexpected
        # exception must not strand a project claimed by this invocation.
        if project_claimed and (not leave_running or execution_failed or not sequence_completed):
            cleanup_status = _cleanup_services(
                project_name=project_name,
                environment_file=environment_file,
                environment=child_environment,
                runner=runner,
                steps=steps,
            )
            if cleanup_status == "failed":
                execution_failed = True
    if not authenticated_post_start:
        for name in (
            "prepare_approved_data",
            "authenticated_rbac_smoke",
            "scheduled_job_validation",
            "notification_validation",
            "analytics_validation",
        ):
            steps.append(
                RehearsalStep(
                    name=name,
                    status="not_executed",
                    duration_ms=None,
                    evidence_code="authenticated_post_start_not_requested",
                )
            )
        execution_failed = True

    overall: Literal["passed", "failed"] = (
        "failed" if execution_failed or not sequence_completed else "passed"
    )

    report = RehearsalReport(
        schema_version=1,
        generated_at=_utc_now(),
        scope="approved-pilot-host-rehearsal",
        executed=True,
        host_approved=True,
        host_identifier=environment["PILOT_HOST_IDENTIFIER"],
        intended_host_claim=intended_host,
        production_readiness_claim=False,
        release_identifier=environment["RELEASE_IDENTIFIER"],
        release_commit=environment["RELEASE_GIT_COMMIT"],
        release_tag=environment["RELEASE_GIT_TAG"],
        alembic_revision=environment["RELEASE_ALEMBIC_REVISION"],
        data_mode=data_mode,
        approved_data_evidence_id=(
            os.getenv(_APPROVED_DATA_EVIDENCE_ENV) if authenticated_post_start else None
        ),
        manifest_sha256=contract.manifest_sha256,
        contract_decision=contract.decision,
        overall_status=overall,
        cleanup_status=cleanup_status,
        steps=tuple(steps),
    )
    report_path = _write_evidence(output_root, report)
    return report, report_path


def cleanup_deployment_rehearsal(
    *,
    environment_file: Path,
    project_name: str = "pm9-pilot-rehearsal",
    runner: CommandRunner = subprocess.run,
) -> Literal["completed", "failed"]:
    """Remove the dedicated pilot project while preserving persistent volumes."""

    environment = os.environ.copy()
    environment.update(load_environment_file(environment_file))
    steps: list[RehearsalStep] = []
    return _cleanup_services(
        project_name=project_name,
        environment_file=environment_file,
        environment=environment,
        runner=runner,
        steps=steps,
    )


def _planned_report(
    *,
    environment: Mapping[str, str],
    data_mode: DataMode,
    contract: ValidationReport,
    host_approved: bool,
    intended_host: bool,
) -> RehearsalReport:
    names = (
        "validate_release_inputs",
        "validate_compose",
        "validate_project_absent",
        "build_release_images",
        "start_dependencies",
        "apply_alembic_migrations",
        "validate_migration_revision",
        "prepare_approved_data",
        "start_application",
        "api_liveness",
        "api_readiness",
        "worker_readiness",
        "qdrant_readiness",
        "frontend_availability",
        "authenticated_rbac_smoke",
        "scheduled_job_validation",
        "notification_validation",
        "analytics_validation",
        "record_evidence",
        "cleanup",
    )
    return RehearsalReport(
        schema_version=1,
        generated_at=_utc_now(),
        scope="deployment-rehearsal-plan",
        executed=False,
        host_approved=host_approved,
        host_identifier=environment["PILOT_HOST_IDENTIFIER"],
        intended_host_claim=intended_host,
        production_readiness_claim=False,
        release_identifier=environment["RELEASE_IDENTIFIER"],
        release_commit=environment["RELEASE_GIT_COMMIT"],
        release_tag=environment["RELEASE_GIT_TAG"],
        alembic_revision=environment["RELEASE_ALEMBIC_REVISION"],
        data_mode=data_mode,
        approved_data_evidence_id=None,
        manifest_sha256=contract.manifest_sha256,
        contract_decision=contract.decision,
        overall_status="not_executed",
        cleanup_status="not_executed",
        steps=tuple(RehearsalStep(name, "not_executed", None, "planned") for name in names),
    )


def _run_step(
    *,
    name: str,
    operation: Sequence[str],
    project_name: str,
    environment_file: Path,
    environment: Mapping[str, str],
    runner: CommandRunner,
    steps: list[RehearsalStep],
) -> None:
    started = time.monotonic()
    command = compose_command(
        project_name=project_name,
        environment_file=environment_file,
        operation=operation,
    )
    try:
        runner(
            command,
            cwd=_REPOSITORY_ROOT,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        steps.append(
            RehearsalStep(
                name=name,
                status="failed",
                duration_ms=_elapsed_ms(started),
                evidence_code="command_failed",
            )
        )
        raise DeploymentRehearsalError(f"Rehearsal step {name} failed safely.") from exc
    steps.append(
        RehearsalStep(
            name=name,
            status="passed",
            duration_ms=_elapsed_ms(started),
            evidence_code="command_completed",
        )
    )


def _validate_project_absent(
    *,
    project_name: str,
    environment_file: Path,
    environment: Mapping[str, str],
    runner: CommandRunner,
    steps: list[RehearsalStep],
) -> None:
    """Refuse to adopt or remove containers created by another invocation."""

    started = time.monotonic()
    command = compose_command(
        project_name=project_name,
        environment_file=environment_file,
        operation=("ps", "--all", "--services"),
    )
    try:
        result = runner(
            command,
            cwd=_REPOSITORY_ROOT,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        steps.append(
            RehearsalStep(
                name="validate_project_absent",
                status="failed",
                duration_ms=_elapsed_ms(started),
                evidence_code="project_collision_check_failed",
            )
        )
        raise DeploymentRehearsalError(
            "Unable to prove that the rehearsal project namespace is unused."
        ) from exc
    if result.stdout.strip():
        steps.append(
            RehearsalStep(
                name="validate_project_absent",
                status="failed",
                duration_ms=_elapsed_ms(started),
                evidence_code="project_namespace_in_use",
            )
        )
        raise DeploymentRehearsalError(
            "The rehearsal project namespace already contains containers."
        )
    steps.append(
        RehearsalStep(
            name="validate_project_absent",
            status="passed",
            duration_ms=_elapsed_ms(started),
            evidence_code="project_namespace_unused",
        )
    )


def _validate_migration_revision(
    *,
    expected_revision: str,
    project_name: str,
    environment_file: Path,
    environment: Mapping[str, str],
    runner: CommandRunner,
    steps: list[RehearsalStep],
) -> None:
    started = time.monotonic()
    operation = (
        "run",
        "--rm",
        "--no-deps",
        "migrate",
        "python",
        "-m",
        "alembic",
        "current",
    )
    command = compose_command(
        project_name=project_name,
        environment_file=environment_file,
        operation=operation,
    )
    try:
        result = runner(
            command,
            cwd=_REPOSITORY_ROOT,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        steps.append(
            RehearsalStep(
                name="validate_migration_revision",
                status="failed",
                duration_ms=_elapsed_ms(started),
                evidence_code="migration_revision_command_failed",
            )
        )
        raise DeploymentRehearsalError("Migration revision validation failed safely.") from exc
    observed_revisions = [
        line.split(maxsplit=1)[0] for line in result.stdout.splitlines() if line.strip()
    ]
    if observed_revisions != [expected_revision]:
        steps.append(
            RehearsalStep(
                name="validate_migration_revision",
                status="failed",
                duration_ms=_elapsed_ms(started),
                evidence_code="migration_revision_mismatch",
            )
        )
        raise DeploymentRehearsalError("Deployed migration revision does not match the release.")
    steps.append(
        RehearsalStep(
            name="validate_migration_revision",
            status="passed",
            duration_ms=_elapsed_ms(started),
            evidence_code="migration_revision_matched",
        )
    )


def _probe_step(
    *,
    name: str,
    url: str,
    expected_status: str | None,
    expected_release: str | None,
    probe: Probe,
    steps: list[RehearsalStep],
) -> None:
    started = time.monotonic()
    deadline = started + 90
    while time.monotonic() < deadline:
        ok, payload = probe(url)
        if ok and _probe_payload_matches(
            payload,
            expected_status=expected_status,
            expected_release=expected_release,
        ):
            steps.append(
                RehearsalStep(
                    name=name,
                    status="passed",
                    duration_ms=_elapsed_ms(started),
                    evidence_code="probe_ready",
                )
            )
            return
        time.sleep(1)
    steps.append(
        RehearsalStep(
            name=name,
            status="failed",
            duration_ms=_elapsed_ms(started),
            evidence_code="probe_timeout",
        )
    )
    raise DeploymentRehearsalError(f"Rehearsal probe {name} did not become ready.")


def _probe_payload_matches(
    payload: Mapping[str, Any] | None,
    *,
    expected_status: str | None,
    expected_release: str | None,
) -> bool:
    if expected_status is None:
        return True
    if not isinstance(payload, Mapping) or payload.get("status") != expected_status:
        return False
    if expected_release is None:
        return True
    release = payload.get("release")
    return isinstance(release, Mapping) and release.get("identifier") == expected_release


def _http_probe(url: str) -> tuple[bool, dict[str, Any] | None]:
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=3) as response:  # noqa: S310 - validated origin
            if response.status != 200:
                return False, None
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                return True, None
            payload = json.loads(response.read(64 * 1024))
            return True, payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return False, None


def _cleanup_services(
    *,
    project_name: str,
    environment_file: Path,
    environment: Mapping[str, str],
    runner: CommandRunner,
    steps: list[RehearsalStep],
) -> Literal["completed", "failed"]:
    try:
        _run_step(
            name="cleanup_remove_services",
            operation=("down", "--remove-orphans"),
            project_name=project_name,
            environment_file=environment_file,
            environment=environment,
            runner=runner,
            steps=steps,
        )
    except DeploymentRehearsalError:
        return "failed"
    return "completed"


def _validate_authenticated_post_start_inputs(
    *,
    environment: Mapping[str, str],
    manifest_path: Path,
    intended_host: bool,
) -> None:
    if os.getenv(_POST_START_EXECUTION_FLAG) != "true":
        raise DeploymentRehearsalError(
            f"Authenticated post-start requires {_POST_START_EXECUTION_FLAG}=true."
        )
    if os.getenv(_APPROVED_DATA_FLAG) != "true":
        raise DeploymentRehearsalError(
            f"Authenticated post-start requires {_APPROVED_DATA_FLAG}=true."
        )
    evidence_id = os.getenv(_APPROVED_DATA_EVIDENCE_ENV, "")
    if not _EVIDENCE_ID_PATTERN.fullmatch(evidence_id):
        raise DeploymentRehearsalError(
            "Approved-data evidence requires one opaque evidence identifier."
        )
    if any(not os.getenv(name) for name in _SMOKE_CREDENTIAL_ENVIRONMENTS):
        raise DeploymentRehearsalError(
            "Authenticated post-start smoke credentials are unavailable."
        )
    from src.reliability.post_start_validation import (
        PostStartValidationError,
        validate_post_start_preconditions,
    )

    try:
        validate_post_start_preconditions(
            base_url=environment["NEXT_PUBLIC_API_BASE_URL"],
            operator_username=os.environ["PM9_SMOKE_OPERATOR_USERNAME"],
            operator_password=os.environ["PM9_SMOKE_OPERATOR_PASSWORD"],
            restricted_username=os.environ["PM9_SMOKE_RESTRICTED_USERNAME"],
            restricted_password=os.environ["PM9_SMOKE_RESTRICTED_PASSWORD"],
            expected_release_identifier=environment["RELEASE_IDENTIFIER"],
            expected_release_commit=environment["RELEASE_GIT_COMMIT"],
            expected_release_tag=environment["RELEASE_GIT_TAG"],
            expected_alembic_revision=environment["RELEASE_ALEMBIC_REVISION"],
            manifest_path=manifest_path,
            refresh_cookie_name=environment.get(
                "REFRESH_COOKIE_NAME",
                "maintenance_refresh",
            ),
            csrf_cookie_name=environment.get("CSRF_COOKIE_NAME", "maintenance_csrf"),
            host_approved=_truthy(environment.get(_HOST_APPROVAL_FLAG)),
            intended_host=intended_host,
            allow_loopback_http=os.getenv("PM9_ALLOW_HTTP_TEST_SMOKE") == "true",
        )
    except PostStartValidationError as exc:
        raise DeploymentRehearsalError("Authenticated post-start preflight failed safely.") from exc


def _run_authenticated_post_start(
    *,
    environment: Mapping[str, str],
    manifest_path: Path,
    evidence_dir: Path,
    intended_host: bool,
):
    # Local import avoids making the reusable post-start validator depend on a
    # second dotenv implementation.
    from src.reliability.post_start_validation import (
        PostStartValidationError,
        run_post_start_validation,
    )

    try:
        report, _ = run_post_start_validation(
            base_url=environment["NEXT_PUBLIC_API_BASE_URL"],
            operator_username=os.environ["PM9_SMOKE_OPERATOR_USERNAME"],
            operator_password=os.environ["PM9_SMOKE_OPERATOR_PASSWORD"],
            restricted_username=os.environ["PM9_SMOKE_RESTRICTED_USERNAME"],
            restricted_password=os.environ["PM9_SMOKE_RESTRICTED_PASSWORD"],
            expected_release_identifier=environment["RELEASE_IDENTIFIER"],
            expected_release_commit=environment["RELEASE_GIT_COMMIT"],
            expected_release_tag=environment["RELEASE_GIT_TAG"],
            expected_alembic_revision=environment["RELEASE_ALEMBIC_REVISION"],
            manifest_path=manifest_path,
            refresh_cookie_name=environment.get(
                "REFRESH_COOKIE_NAME",
                "maintenance_refresh",
            ),
            csrf_cookie_name=environment.get("CSRF_COOKIE_NAME", "maintenance_csrf"),
            evidence_dir=evidence_dir,
            host_approved=_truthy(environment.get(_HOST_APPROVAL_FLAG)),
            intended_host=intended_host,
            allow_loopback_http=os.getenv("PM9_ALLOW_HTTP_TEST_SMOKE") == "true",
        )
    except PostStartValidationError as exc:
        raise DeploymentRehearsalError(
            "Authenticated post-start validation failed safely."
        ) from exc
    return report


def _append_post_start_steps(
    report,
    *,
    steps: list[RehearsalStep],
) -> None:
    by_name = {check.name: check.status for check in report.checks}
    mappings = (
        (
            "prepare_approved_data",
            ("approved_data_reads",),
            "approved_data_attested_and_runtime_records_validated",
        ),
        (
            "authenticated_rbac_smoke",
            (
                "unauthenticated_boundary",
                "operator_authentication",
                "operator_session_refresh",
                "restricted_authentication",
                "rbac_boundary",
            ),
            "authentication_session_and_rbac_validated",
        ),
        (
            "scheduled_job_validation",
            ("release_and_readiness", "scheduled_jobs"),
            "worker_and_exact_job_catalog_validated",
        ),
        (
            "notification_validation",
            ("notification_owner_isolation",),
            "nonempty_owner_isolated_notifications_validated",
        ),
        (
            "analytics_validation",
            ("analytics_availability",),
            "batch_analytics_availability_validated",
        ),
    )
    failed = report.overall_status != "passed"
    for step_name, required_checks, evidence_code in mappings:
        passed = all(by_name.get(name) == "passed" for name in required_checks)
        steps.append(
            RehearsalStep(
                name=step_name,
                status="passed" if passed else "failed",
                duration_ms=None,
                evidence_code=evidence_code if passed else "post_start_check_failed",
            )
        )
        failed |= not passed
    if failed:
        raise DeploymentRehearsalError("Authenticated post-start validation failed safely.")


def _validate_release_environment(environment: Mapping[str, str]) -> None:
    required = (
        "RELEASE_IDENTIFIER",
        "RELEASE_GIT_COMMIT",
        "RELEASE_GIT_TAG",
        "RELEASE_ALEMBIC_REVISION",
        "PILOT_HOST_IDENTIFIER",
        "NEXT_PUBLIC_API_BASE_URL",
        "FRONTEND_BASE_URL",
    )
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise DeploymentRehearsalError(
            "Pilot environment is missing required release or endpoint variables."
        )
    for name in required[:5]:
        value = environment[name].upper()
        if any(marker in value for marker in _PLACEHOLDER_MARKERS):
            raise DeploymentRehearsalError(
                f"Pilot environment variable {name} still contains a placeholder."
            )
    if not _COMMIT_PATTERN.fullmatch(environment["RELEASE_GIT_COMMIT"]):
        raise DeploymentRehearsalError(
            "RELEASE_GIT_COMMIT must be a 40-character lowercase commit."
        )
    if not _HOST_IDENTIFIER_PATTERN.fullmatch(environment["PILOT_HOST_IDENTIFIER"]):
        raise DeploymentRehearsalError("PILOT_HOST_IDENTIFIER must be a bounded opaque identifier.")
    for name in ("NEXT_PUBLIC_API_BASE_URL", "FRONTEND_BASE_URL"):
        _credential_free_origin(environment[name], name)


def _validate_data_mode(data_mode: DataMode, environment: Mapping[str, str]) -> None:
    if data_mode == "existing_approved":
        return
    if data_mode != "empty_test":
        raise ValueError("Unsupported data mode.")
    database_name = environment.get("POSTGRES_DB", "")
    if not database_name.endswith("_test") or os.getenv(_EMPTY_DATA_FLAG) != "true":
        raise DeploymentRehearsalError(
            f"Empty-data rehearsal requires a _test database and {_EMPTY_DATA_FLAG}=true."
        )


def _credential_free_origin(value: str, name: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentRehearsalError(f"{name} must be a credential-free HTTP(S) origin.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _bound_endpoint(
    environment: Mapping[str, str],
    address_name: str,
    port_name: str,
    path: str,
) -> str:
    address = environment.get(address_name, "")
    if address in {"0.0.0.0", "::", "[::]"}:
        address = "127.0.0.1"
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    try:
        port = int(environment.get(port_name, ""))
    except ValueError as exc:
        raise DeploymentRehearsalError(f"{port_name} must be a valid TCP port.") from exc
    if not address or not 1 <= port <= 65535:
        raise DeploymentRehearsalError(
            "Pilot bind address and port must be configured for health probes."
        )
    return f"http://{address}:{port}{path}"


def _validated_evidence_dir(value: Path | None) -> Path:
    if value is None:
        raise DeploymentRehearsalError(
            "An outside-repository evidence directory is required for execution."
        )
    resolved = value.resolve()
    if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
        raise DeploymentRehearsalError(
            "Raw rehearsal evidence must be written outside the repository."
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_evidence(root: Path, report: RehearsalReport) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = root / f"pm9-deployment-rehearsal-{stamp}.json"
    temporary = path.with_suffix(".partial")
    temporary.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _git_output(
    command: Sequence[str],
    *,
    runner: CommandRunner,
    required: bool = True,
) -> str | None:
    try:
        result = runner(
            tuple(command),
            cwd=_REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if required:
            raise DeploymentRehearsalError("Git release identity is unavailable.") from exc
        return None
    value = result.stdout.strip()
    if required and not value:
        raise DeploymentRehearsalError("Git release identity is empty.")
    return value or None


def _validate_clean_release_worktree(*, runner: CommandRunner) -> None:
    """Bind the Docker build context to the exact checked-out tagged commit."""

    command = (
        "git",
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
    )
    try:
        result = runner(
            command,
            cwd=_REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DeploymentRehearsalError("Git worktree cleanliness is unavailable.") from exc
    if result.stdout.strip():
        raise DeploymentRehearsalError("Deployment execution requires a clean release worktree.")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_REPOSITORY_ROOT / "deployment" / "pilot_manifest.json",
    )
    parser.add_argument("--project-name", default="pm9-pilot-rehearsal")
    parser.add_argument(
        "--data-mode",
        choices=("existing_approved", "empty_test"),
        default="existing_approved",
    )
    parser.add_argument("--evidence-dir", type=Path)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--execute", action="store_true")
    execution.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--leave-running", action="store_true")
    parser.add_argument("--intended-host", action="store_true")
    parser.add_argument("--authenticated-post-start", action="store_true")
    args = parser.parse_args(argv)
    if args.cleanup_only:
        if (
            args.leave_running
            or args.intended_host
            or args.authenticated_post_start
            or args.evidence_dir
        ):
            parser.error("--cleanup-only cannot be combined with rehearsal-only options.")
        cleanup_status = cleanup_deployment_rehearsal(
            environment_file=args.environment_file,
            project_name=args.project_name,
        )
        print(
            json.dumps(
                {
                    "executed": True,
                    "scope": "non_destructive_cleanup",
                    "cleanup_status": cleanup_status,
                    "volumes_removed": False,
                },
                sort_keys=True,
            )
        )
        return 0 if cleanup_status == "completed" else 2
    report, report_path = run_deployment_rehearsal(
        environment_file=args.environment_file,
        manifest_path=args.manifest,
        project_name=args.project_name,
        data_mode=args.data_mode,
        evidence_dir=args.evidence_dir,
        execute=args.execute,
        leave_running=args.leave_running,
        intended_host=args.intended_host,
        authenticated_post_start=args.authenticated_post_start,
    )
    print(
        json.dumps(
            {
                "executed": report.executed,
                "status": report.overall_status,
                "contract_decision": report.contract_decision,
                "evidence_written": report_path is not None,
                "cleanup_status": report.cleanup_status,
            },
            sort_keys=True,
        )
    )
    return 0 if not report.executed or report.overall_status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
