"""Network-free safety and contract tests for the PM9 mutation rehearsal."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from src.reliability.mutation_rehearsal import (
    MutationAction,
    MutationPlan,
    ResponseAssertion,
    load_mutation_plan,
    run_mutation_rehearsal,
)

_DATABASE_NAME = "pilot_pm9_test"
_DATABASE_URL = "postgresql+psycopg://pm9_user:synthetic-password@db.example.test/pilot_pm9_test"
_DATABASE_FINGERPRINT = hashlib.sha256(
    f"pm9-test-database:{_DATABASE_NAME}".encode("utf-8")
).hexdigest()


def _plan(namespace: str = "pm9-bounded-001") -> MutationPlan:
    return MutationPlan(
        namespace=namespace,
        actions=(
            MutationAction(
                action_id="create_ticket",
                operation="ticket_create",
                method="POST",
                path_template="/tickets/intake",
                expected_statuses=(201,),
                json_body_template={
                    "external_reference": namespace,
                    "title": "Bản ghi diễn tập cô lập",
                },
                idempotency_key=f"{namespace}:ticket:create",
                captures={"ticket_id": "id", "ticket_version": "version"},
                replay=True,
                replay_expected_statuses=(200, 201),
                replay_match_paths=("id",),
            ),
            MutationAction(
                action_id="stale_version_probe",
                operation="optimistic_concurrency_probe",
                method="POST",
                path_template="/tickets/${ticket_id}/assign",
                expected_statuses=(409,),
                json_body_template={"expected_version": 0},
                idempotency_key=f"{namespace}:ticket:stale-version",
            ),
            MutationAction(
                action_id="inventory_nonnegative",
                operation="invariant_inventory_nonnegative",
                method="GET",
                path_template="/inventory/balances?page=1&page_size=100",
                expected_statuses=(200,),
                assertions=(
                    ResponseAssertion("on_hand_quantity", "gte", "0"),
                    ResponseAssertion("reserved_quantity", "gte", "0"),
                    ResponseAssertion("available_quantity", "gte", "0"),
                ),
            ),
            MutationAction(
                action_id="notification_uniqueness",
                operation="invariant_notifications_unique",
                method="GET",
                path_template="/notifications?page=1&page_size=100",
                expected_statuses=(200,),
                assertions=(ResponseAssertion("items", "unique", "id"),),
            ),
        ),
        cleanup_actions=(
            MutationAction(
                action_id="cancel_ticket",
                operation="cleanup_ticket",
                method="POST",
                path_template="/tickets/${ticket_id}/cancel",
                expected_statuses=(200,),
                json_body_template={
                    "expected_version": "${ticket_version}",
                    "reason": namespace,
                },
                idempotency_key=f"{namespace}:cleanup:ticket",
            ),
        ),
    )


def _success_transport(
    *,
    calls: list[tuple[str, str, str | None]],
    secret_token: str,
    notification_hook: Callable[[], None] | None = None,
    notification_ids: tuple[str, ...] = ("notification-1", "notification-2"),
) -> httpx.MockTransport:
    create_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal create_count
        calls.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Idempotency-Key"),
            )
        )
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": secret_token})
        if request.url.path == "/health/live":
            return httpx.Response(
                200,
                json={
                    "status": "alive",
                    "test_database_fingerprint": _DATABASE_FINGERPRINT,
                },
            )
        assert request.headers["Authorization"] == f"Bearer {secret_token}"
        if request.url.path == "/tickets/intake":
            create_count += 1
            return httpx.Response(
                201 if create_count == 1 else 200,
                json={"id": "TKT-PM9-001", "version": 1, "created": create_count == 1},
            )
        if request.url.path.endswith("/assign"):
            return httpx.Response(409, json={"detail": "stale version"})
        if request.url.path == "/inventory/balances":
            return httpx.Response(
                200,
                json={
                    "on_hand_quantity": "3",
                    "reserved_quantity": "1",
                    "available_quantity": "2",
                },
            )
        if request.url.path == "/notifications":
            if notification_hook is not None:
                notification_hook()
            return httpx.Response(
                200,
                json={"items": [{"id": identifier} for identifier in notification_ids]},
            )
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "TKT-PM9-001", "status": "cancelled"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    return httpx.MockTransport(handler)


def test_mutation_rehearsal_requires_opt_in_and_test_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PM9_ALLOW_MUTATION_REHEARSAL", raising=False)
    with pytest.raises(RuntimeError, match="PM9_ALLOW_MUTATION_REHEARSAL"):
        run_mutation_rehearsal(
            plan=_plan(),
            database_url=_DATABASE_URL,
            base_url="http://pilot.example.test",
            username="pm9.test",
            password="synthetic-password",
            output_dir=tmp_path,
        )

    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    with pytest.raises(ValueError, match="must end with _test"):
        run_mutation_rehearsal(
            plan=_plan(),
            database_url=(
                "postgresql+psycopg://pm9_user:synthetic-password@"
                "db.example.test/developer_database"
            ),
            base_url="http://pilot.example.test",
            username="pm9.test",
            password="synthetic-password",
            output_dir=tmp_path,
        )


def test_mutation_rehearsal_rejects_api_database_attestation_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    authenticated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authenticated
        if request.url.path == "/health/live":
            return httpx.Response(
                200,
                json={
                    "status": "alive",
                    "test_database_fingerprint": "0" * 64,
                },
            )
        if request.url.path == "/auth/login":
            authenticated = True
        raise AssertionError("A mismatched target must be rejected before authentication.")

    with pytest.raises(RuntimeError, match="not attested"):
        run_mutation_rehearsal(
            plan=_plan(),
            database_url=_DATABASE_URL,
            base_url="http://pilot.example.test",
            username="pm9.test",
            password="synthetic-password",
            output_dir=tmp_path / "evidence",
            canonical_data_roots=(),
            transport=httpx.MockTransport(handler),
        )
    assert authenticated is False


def test_plan_requires_namespaced_stable_keys_cleanup_conflict_and_invariants() -> None:
    with pytest.raises(ValueError, match="scoped to the test namespace"):
        MutationPlan(
            namespace="pm9-bounded-001",
            actions=(
                MutationAction(
                    action_id="create_ticket",
                    operation="ticket_create",
                    method="POST",
                    path_template="/tickets/intake",
                    expected_statuses=(201,),
                    idempotency_key="wrong-namespace",
                    replay=True,
                    replay_match_paths=("id",),
                ),
                MutationAction(
                    action_id="stale_version_probe",
                    operation="optimistic_concurrency_probe",
                    method="POST",
                    path_template="/tickets/TKT/assign",
                    expected_statuses=(409,),
                    idempotency_key="pm9-bounded-001:conflict",
                ),
                MutationAction(
                    action_id="inventory_nonnegative",
                    operation="invariant_inventory_nonnegative",
                    method="GET",
                    path_template="/inventory/balances",
                    expected_statuses=(200,),
                ),
            ),
            cleanup_actions=(
                MutationAction(
                    action_id="cancel_ticket",
                    operation="cleanup_ticket",
                    method="POST",
                    path_template="/tickets/TKT/cancel",
                    expected_statuses=(200,),
                    idempotency_key="pm9-bounded-001:cleanup",
                ),
            ),
        )

    with pytest.raises(ValueError, match="Unsupported"):
        MutationAction(
            action_id="arbitrary_action",
            operation="arbitrary_sql",
            method="POST",
            path_template="/operations/arbitrary",
            expected_statuses=(200,),
            idempotency_key="pm9-bounded-001:arbitrary",
        )
    with pytest.raises(ValueError, match="not bound"):
        MutationAction(
            action_id="mislabelled_cleanup",
            operation="cleanup_ticket",
            method="POST",
            path_template="/operations/jobs/sla_escalation/trigger",
            expected_statuses=(200,),
            idempotency_key="pm9-bounded-001:mislabelled",
        )


def test_declarative_plan_loader_is_bounded_and_rejects_credential_fields(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "mutation-plan.json"
    raw = asdict(_plan())
    fixture.write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_mutation_plan(fixture)
    assert loaded.namespace == "pm9-bounded-001"
    assert loaded.maximum_http_requests == 7

    raw["actions"][0]["json_body_template"]["password"] = "must-not-be-accepted"
    fixture.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="credential-bearing"):
        load_mutation_plan(fixture)

    with pytest.raises(ValueError, match="regular file"):
        load_mutation_plan(tmp_path / "missing-plan.json")


def test_successful_rehearsal_replays_checks_conflict_invariants_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    canonical_file = canonical_root / "assets.csv"
    canonical_file.write_text("asset_id\nASSET-001\n", encoding="utf-8")
    output_dir = tmp_path / "evidence"
    calls: list[tuple[str, str, str | None]] = []
    token = "synthetic-bearer-token-that-must-not-be-persisted"

    report, report_path = run_mutation_rehearsal(
        plan=_plan(),
        database_url=_DATABASE_URL,
        base_url="http://pilot.example.test",
        username="pm9.test",
        password="synthetic-login-password-that-must-not-be-persisted",
        output_dir=output_dir,
        canonical_data_roots=(canonical_root,),
        transport=_success_transport(calls=calls, secret_token=token),
    )

    assert report["overall_passed"] is True
    assert report["test_database_suffix_verified"] is True
    assert report["api_database_attestation_verified"] is True
    assert report["idempotent_replays_passed"] is True
    assert report["optimistic_concurrency_checked"] is True
    assert report["invariants_passed"] is True
    assert report["cleanup_actions_complete"] is True
    assert report["isolated_database_teardown_required"] is True
    assert report["test_records_removed_claim"] is False
    assert report["canonical_data_unchanged"] is True
    assert report["maximum_http_requests"] == 7
    assert report["workload_metrics"]["mutation_attempted_count"] == 2
    assert report["workload_metrics"]["mutation_success_rate"] == 1.0
    assert report["workload_metrics"]["expected_conflict_observed_count"] == 1
    assert report["workload_metrics"]["idempotent_replay_count"] == 1
    assert report["workload_metrics"]["unexpected_failure_rate"] == 0.0
    assert calls[-1][1] == "/tickets/TKT-PM9-001/cancel"
    create_keys = [key for method, path, key in calls if path == "/tickets/intake"]
    assert create_keys == [
        "pm9-bounded-001:ticket:create",
        "pm9-bounded-001:ticket:create",
    ]

    serialized = report_path.read_text(encoding="utf-8")
    assert token not in serialized
    assert "synthetic-login-password" not in serialized
    assert "synthetic-password" not in serialized
    assert "Authorization" not in serialized
    assert "Idempotency-Key" not in serialized
    assert str(canonical_root.resolve()) not in serialized


def test_action_failure_stops_workload_but_still_attempts_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    cleanup_called = False
    create_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cleanup_called, create_count
        if request.url.path == "/health/live":
            return httpx.Response(
                200,
                json={
                    "status": "alive",
                    "test_database_fingerprint": _DATABASE_FINGERPRINT,
                },
            )
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "ephemeral"})
        if request.url.path == "/tickets/intake":
            create_count += 1
            return httpx.Response(
                201 if create_count == 1 else 200,
                json={"id": "TKT-PM9-001", "version": 1},
            )
        if request.url.path.endswith("/assign"):
            return httpx.Response(500, json={"detail": "synthetic failure"})
        if request.url.path.endswith("/cancel"):
            cleanup_called = True
            return httpx.Response(200, json={"status": "cancelled"})
        raise AssertionError("Later workload actions must not run after an unexpected result.")

    report, _ = run_mutation_rehearsal(
        plan=_plan(),
        database_url=_DATABASE_URL,
        base_url="http://pilot.example.test",
        username="pm9.test",
        password="synthetic-password",
        output_dir=tmp_path / "evidence",
        canonical_data_roots=(),
        transport=httpx.MockTransport(handler),
    )

    assert report["workload_passed"] is False
    assert report["attempted_workload_actions"] == 2
    assert cleanup_called is True
    assert report["cleanup_actions_complete"] is True
    assert report["overall_passed"] is False


def test_committed_but_uncaptured_fixture_never_reports_cleanup_complete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    cleanup_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cleanup_called
        if request.url.path == "/health/live":
            return httpx.Response(
                200,
                json={
                    "status": "alive",
                    "test_database_fingerprint": _DATABASE_FINGERPRINT,
                },
            )
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "ephemeral"})
        if request.url.path == "/tickets/intake":
            # Simulate a committed mutation whose response cannot provide the
            # identifier required by the cleanup action.
            return httpx.Response(201, json={"version": 1})
        cleanup_called = True
        raise AssertionError("Cleanup without a captured identifier must not call the API.")

    report, _ = run_mutation_rehearsal(
        plan=_plan(),
        database_url=_DATABASE_URL,
        base_url="http://pilot.example.test",
        username="pm9.test",
        password="synthetic-password",
        output_dir=tmp_path / "evidence",
        canonical_data_roots=(),
        transport=httpx.MockTransport(handler),
    )

    assert cleanup_called is False
    assert report["cleanup_actions_complete"] is False
    assert report["cleanup_actions"][0]["outcome"] == ("cleanup_uncertain_missing_fixture_context")
    assert report["isolated_database_teardown_required"] is True
    assert report["overall_passed"] is False


def test_duplicate_invariant_and_canonical_drift_fail_the_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_MUTATION_REHEARSAL", "true")
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    canonical_file = canonical_root / "assets.csv"
    canonical_file.write_text("before", encoding="utf-8")
    calls: list[tuple[str, str, str | None]] = []

    report, report_path = run_mutation_rehearsal(
        plan=_plan(),
        database_url=_DATABASE_URL,
        base_url="http://pilot.example.test",
        username="pm9.test",
        password="synthetic-password",
        output_dir=tmp_path / "evidence",
        canonical_data_roots=(canonical_root,),
        transport=_success_transport(
            calls=calls,
            secret_token="ephemeral",
            notification_hook=lambda: canonical_file.write_text("after", encoding="utf-8"),
            notification_ids=("duplicate", "duplicate"),
        ),
    )

    assert report["invariants_passed"] is False
    assert report["canonical_data_unchanged"] is False
    assert report["overall_passed"] is False
    loaded: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["production_readiness_claim"] is False
    assert loaded["pilot_host_execution_claim"] is False
