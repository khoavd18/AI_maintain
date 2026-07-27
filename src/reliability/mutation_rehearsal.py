"""Bounded authenticated mutation rehearsal for an isolated PostgreSQL test stack."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from sqlalchemy.engine import make_url

from src.reliability.load_harness import (
    _validated_base_url,
    _validated_report_directory,
    _validated_request_path,
    _write_report,
)

_OPT_IN_FLAG = "PM9_ALLOW_MUTATION_REHEARSAL"
_NAMESPACE_PATTERN = re.compile(r"^pm9-[a-z0-9][a-z0-9-]{5,47}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PLACEHOLDER_PATTERN = re.compile(r"\$\{([a-z][a-z0-9_]{2,63})\}")
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ALLOWED_OPERATIONS = frozenset(
    {
        "ticket_create",
        "ticket_assign",
        "ticket_transition",
        "ticket_comment",
        "work_order_create",
        "work_order_transition",
        "inventory_receipt",
        "inventory_transfer",
        "notification_read",
        "notification_unread",
        "notification_dismiss",
        "job_trigger",
        "dead_letter_redrive",
        "optimistic_concurrency_probe",
        "invariant_inventory_nonnegative",
        "invariant_effect_unique",
        "invariant_outbox_drained",
        "invariant_notifications_unique",
        "cleanup_ticket",
        "cleanup_work_order",
        "cleanup_inventory_fixture",
        "cleanup_notification",
    }
)
_INVARIANT_OPERATIONS = frozenset(
    operation for operation in _ALLOWED_OPERATIONS if operation.startswith("invariant_")
)
_CANONICAL_DATA_ROOTS = (
    Path("data/raw"),
    Path("data/processed"),
)
_FORBIDDEN_PLAN_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)
_PATH_SEGMENT = (
    r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}|"
    r"\$\{[a-z][a-z0-9_]{2,63}\})"
)
_OPERATION_CONTRACTS: dict[str, tuple[str, tuple[re.Pattern[str], ...]]] = {
    "ticket_create": ("POST", (re.compile(r"^/tickets/intake$"),)),
    "ticket_assign": (
        "POST",
        (re.compile(rf"^/tickets/{_PATH_SEGMENT}/assign$"),),
    ),
    "ticket_transition": (
        "POST",
        (
            re.compile(
                rf"^/tickets/{_PATH_SEGMENT}/"
                r"(?:acknowledge|start|hold|resume|resolve|close|reopen|cancel|"
                r"priority|sla-policy)$"
            ),
        ),
    ),
    "ticket_comment": (
        "POST",
        (re.compile(rf"^/tickets/{_PATH_SEGMENT}/comments$"),),
    ),
    "work_order_create": (
        "POST",
        (
            re.compile(r"^/work-orders$"),
            re.compile(rf"^/tickets/{_PATH_SEGMENT}/work-orders$"),
        ),
    ),
    "work_order_transition": (
        "POST",
        (
            re.compile(
                rf"^/work-orders/{_PATH_SEGMENT}/"
                r"(?:assign|transition|checklist|complete|verify|cancel|reopen)$"
            ),
        ),
    ),
    "inventory_receipt": ("POST", (re.compile(r"^/inventory/receipts$"),)),
    "inventory_transfer": ("POST", (re.compile(r"^/inventory/transfers$"),)),
    "notification_read": (
        "POST",
        (re.compile(rf"^/notifications/{_PATH_SEGMENT}/read$"),),
    ),
    "notification_unread": (
        "POST",
        (re.compile(rf"^/notifications/{_PATH_SEGMENT}/unread$"),),
    ),
    "notification_dismiss": (
        "POST",
        (re.compile(rf"^/notifications/{_PATH_SEGMENT}/dismiss$"),),
    ),
    "job_trigger": (
        "POST",
        (
            re.compile(
                r"^/operations/jobs/(?:preventive_generation|sla_escalation|"
                r"analytics_refresh|inventory_reorder_detection)/trigger$"
            ),
        ),
    ),
    "dead_letter_redrive": (
        "POST",
        (re.compile(rf"^/operations/outbox/{_PATH_SEGMENT}/retry$"),),
    ),
    "optimistic_concurrency_probe": (
        "POST",
        (
            re.compile(
                rf"^/tickets/{_PATH_SEGMENT}/"
                r"(?:assign|acknowledge|start|hold|resume|resolve|close|reopen|"
                r"cancel|priority|sla-policy)$"
            ),
            re.compile(
                rf"^/work-orders/{_PATH_SEGMENT}/"
                r"(?:assign|transition|checklist|complete|verify|cancel|reopen)$"
            ),
        ),
    ),
    "invariant_inventory_nonnegative": (
        "GET",
        (re.compile(r"^/inventory/balances$"),),
    ),
    "invariant_effect_unique": (
        "GET",
        (
            re.compile(rf"^/tickets/{_PATH_SEGMENT}$"),
            re.compile(rf"^/work-orders/{_PATH_SEGMENT}$"),
            re.compile(r"^/inventory/movements$"),
            re.compile(r"^/operations/executions$"),
            re.compile(r"^/operations/outbox$"),
        ),
    ),
    "invariant_outbox_drained": (
        "GET",
        (
            re.compile(r"^/operations/metrics$"),
            re.compile(r"^/operations/outbox$"),
        ),
    ),
    "invariant_notifications_unique": (
        "GET",
        (re.compile(r"^/notifications$"),),
    ),
    "cleanup_ticket": (
        "POST",
        (re.compile(rf"^/tickets/{_PATH_SEGMENT}/cancel$"),),
    ),
    "cleanup_work_order": (
        "POST",
        (re.compile(rf"^/work-orders/{_PATH_SEGMENT}/cancel$"),),
    ),
    "cleanup_inventory_fixture": (
        "POST",
        (
            re.compile(rf"^/parts/{_PATH_SEGMENT}/archive$"),
            re.compile(rf"^/stock-locations/{_PATH_SEGMENT}/archive$"),
        ),
    ),
    "cleanup_notification": (
        "POST",
        (re.compile(rf"^/notifications/{_PATH_SEGMENT}/dismiss$"),),
    ),
}


@dataclass(frozen=True)
class ResponseAssertion:
    """One allow-listed assertion over an HTTP JSON response."""

    json_path: str
    operator: Literal["eq", "gte", "lte", "length_eq", "unique", "is_true"]
    expected: Any = None

    def __post_init__(self) -> None:
        if self.operator not in {"eq", "gte", "lte", "length_eq", "unique", "is_true"}:
            raise ValueError(f"Unsupported response assertion operator: {self.operator}.")
        if not self.json_path or any(part == "" for part in self.json_path.split(".")):
            raise ValueError("Assertion JSON paths must contain non-empty components.")
        if self.operator in {"eq", "gte", "lte", "length_eq"} and self.expected is None:
            raise ValueError(f"Assertion operator {self.operator!r} requires an expected value.")
        if (
            self.operator == "unique"
            and self.expected is not None
            and not isinstance(self.expected, str)
        ):
            raise ValueError("A unique assertion field must be a JSON-path string.")


@dataclass(frozen=True)
class MutationAction:
    """One named request in the closed PM9 mutation rehearsal catalog."""

    action_id: str
    operation: str
    method: str
    path_template: str
    expected_statuses: tuple[int, ...]
    json_body_template: Mapping[str, Any] | None = None
    idempotency_key: str | None = None
    captures: Mapping[str, str] = field(default_factory=dict)
    assertions: tuple[ResponseAssertion, ...] = ()
    replay: bool = False
    replay_expected_statuses: tuple[int, ...] | None = None
    replay_match_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        method = self.method.upper()
        object.__setattr__(self, "method", method)
        if not _IDENTIFIER_PATTERN.fullmatch(self.action_id):
            raise ValueError("Action identifiers must use lower snake_case.")
        if self.operation not in _ALLOWED_OPERATIONS:
            raise ValueError(f"Unsupported mutation rehearsal operation: {self.operation}.")
        if method not in _MUTATING_METHODS | {"GET"}:
            raise ValueError("Mutation rehearsal methods are limited to GET/POST/PUT/PATCH/DELETE.")
        _validated_request_path(self.path_template)
        _validate_operation_contract(
            operation=self.operation,
            method=method,
            path_template=self.path_template,
            expected_statuses=self.expected_statuses,
        )
        if not self.expected_statuses or any(
            isinstance(status, bool) or status < 100 or status > 599
            for status in self.expected_statuses
        ):
            raise ValueError("Every action requires valid expected HTTP statuses.")
        if method in _MUTATING_METHODS and not self.idempotency_key:
            raise ValueError("Every mutating rehearsal action requires an Idempotency-Key.")
        if method == "GET" and self.idempotency_key:
            raise ValueError("Read-only rehearsal actions must not send an Idempotency-Key.")
        if self.replay and method not in _MUTATING_METHODS:
            raise ValueError("Only mutating actions can request an idempotency replay.")
        if self.replay and not self.replay_match_paths:
            raise ValueError("Replay actions require at least one stable JSON match path.")
        for context_name, json_path in self.captures.items():
            if not _IDENTIFIER_PATTERN.fullmatch(context_name) or not json_path:
                raise ValueError("Capture names and JSON paths must be explicit.")


@dataclass(frozen=True)
class MutationPlan:
    """Caller-supplied, stable plan for records isolated by a PM9 namespace."""

    namespace: str
    actions: tuple[MutationAction, ...]
    cleanup_actions: tuple[MutationAction, ...]

    def __post_init__(self) -> None:
        if not _NAMESPACE_PATTERN.fullmatch(self.namespace):
            raise ValueError("Mutation namespace must match pm9-[a-z0-9-] and be 9-51 characters.")
        if not self.actions or len(self.actions) > 40:
            raise ValueError("Mutation plans require between 1 and 40 workload actions.")
        if not self.cleanup_actions or len(self.cleanup_actions) > 20:
            raise ValueError("Mutation plans require between 1 and 20 cleanup actions.")
        all_actions = (*self.actions, *self.cleanup_actions)
        action_ids = [action.action_id for action in all_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Mutation action identifiers must be unique within a plan.")
        keys = [
            action.idempotency_key for action in all_actions if action.idempotency_key is not None
        ]
        required_prefix = f"{self.namespace}:"
        if any(not key.startswith(required_prefix) for key in keys):
            raise ValueError("Every Idempotency-Key must be scoped to the test namespace.")
        if len(keys) != len(set(keys)):
            raise ValueError("Caller-stable Idempotency-Keys must be unique across actions.")
        if not any(action.replay for action in self.actions):
            raise ValueError("Mutation plans must include an idempotent replay check.")
        if not any(action.operation == "optimistic_concurrency_probe" for action in self.actions):
            raise ValueError("Mutation plans must include an optimistic-concurrency probe.")
        if not any(action.operation in _INVARIANT_OPERATIONS for action in self.actions):
            raise ValueError("Mutation plans must include at least one invariant check.")
        if any(not action.operation.startswith("cleanup_") for action in self.cleanup_actions):
            raise ValueError("Cleanup actions must use the closed cleanup operation catalog.")

    @property
    def maximum_http_requests(self) -> int:
        """Bound includes login, every action, requested replays, and cleanup."""

        return (
            1
            + len(self.actions)
            + sum(1 for action in self.actions if action.replay)
            + len(self.cleanup_actions)
        )


def load_mutation_plan(path: Path) -> MutationPlan:
    """Load a bounded declarative plan without accepting executable definitions."""

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ValueError("Mutation plan must be a readable regular file.") from exc
    if not path.is_file():
        raise ValueError("Mutation plan must be a readable regular file.")
    if file_size > 128 * 1024:
        raise ValueError("Mutation plan files must not exceed 128 KiB.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Mutation plan must be readable UTF-8 JSON.") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("Mutation plan root must be a JSON object.")
    _require_exact_keys(raw, {"namespace", "actions", "cleanup_actions"}, "plan")
    _reject_secret_fields(raw)
    actions = _parse_action_list(raw["actions"], "actions")
    cleanup_actions = _parse_action_list(raw["cleanup_actions"], "cleanup_actions")
    return MutationPlan(
        namespace=str(raw["namespace"]),
        actions=actions,
        cleanup_actions=cleanup_actions,
    )


@dataclass(frozen=True)
class _ActionResult:
    action_id: str
    operation: str
    phase: Literal["workload", "cleanup"]
    status_code: int | None
    elapsed_ms: float
    passed: bool
    assertion_count: int
    assertions_passed: bool
    replay_status_code: int | None = None
    replay_consistent: bool | None = None
    outcome: str = "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "operation": self.operation,
            "phase": self.phase,
            "status_code": self.status_code,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "passed": self.passed,
            "assertion_count": self.assertion_count,
            "assertions_passed": self.assertions_passed,
            "replay_status_code": self.replay_status_code,
            "replay_consistent": self.replay_consistent,
            "outcome": self.outcome,
        }


def run_mutation_rehearsal(
    *,
    plan: MutationPlan,
    database_url: str,
    base_url: str,
    username: str,
    password: str,
    output_dir: Path | None = None,
    canonical_data_roots: Sequence[Path] = _CANONICAL_DATA_ROOTS,
    timeout_seconds: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], Path]:
    """Execute a bounded test-only plan and emit a secret-free summary report."""

    if os.getenv(_OPT_IN_FLAG) != "true":
        raise RuntimeError(
            f"Mutation rehearsal requires {_OPT_IN_FLAG}=true and an isolated test stack."
        )
    expected_database_fingerprint = _validate_test_database_url(database_url)
    normalized_base_url = _validated_base_url(base_url)
    if not username or not password:
        raise ValueError("Mutation rehearsal requires explicit test credentials.")
    if not 0 < timeout_seconds <= 30:
        raise ValueError("Mutation rehearsal timeout must be between 0 and 30 seconds.")
    report_dir = _validated_report_directory(output_dir)
    before_fingerprints = _fingerprint_roots(canonical_data_roots)
    workload_results: list[_ActionResult] = []
    cleanup_results: list[_ActionResult] = []
    context: dict[str, Any] = {"test_namespace": plan.namespace}
    authentication_succeeded = False

    client_kwargs: dict[str, Any] = {
        "base_url": normalized_base_url,
        "timeout": timeout_seconds,
    }
    if transport is not None:
        client_kwargs["transport"] = transport
    with httpx.Client(**client_kwargs) as client:
        _verify_test_target(
            client,
            expected_database_fingerprint=expected_database_fingerprint,
        )
        token = _login(client, username=username, password=password)
        authentication_succeeded = True
        headers = {"Authorization": f"Bearer {token}"}
        try:
            for action in plan.actions:
                result = _execute_action(
                    client=client,
                    action=action,
                    phase="workload",
                    headers=headers,
                    context=context,
                )
                workload_results.append(result)
                if not result.passed:
                    break
        finally:
            if authentication_succeeded:
                for action in plan.cleanup_actions:
                    cleanup_results.append(
                        _execute_action(
                            client=client,
                            action=action,
                            phase="cleanup",
                            headers=headers,
                            context=context,
                        )
                    )

    after_fingerprints = _fingerprint_roots(canonical_data_roots)
    canonical_data_unchanged = before_fingerprints == after_fingerprints
    workload_complete = len(workload_results) == len(plan.actions)
    workload_passed = workload_complete and all(result.passed for result in workload_results)
    cleanup_actions_complete = len(cleanup_results) == len(plan.cleanup_actions) and all(
        result.passed for result in cleanup_results
    )
    invariant_results = [
        result for result in workload_results if result.operation in _INVARIANT_OPERATIONS
    ]
    replay_results = [result for result in workload_results if result.replay_consistent is not None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "isolated-pm9-mutation-rehearsal",
        "synthetic_or_test_data_only": True,
        "test_namespace": plan.namespace,
        "test_database_suffix_verified": True,
        "api_database_attestation_verified": True,
        "authenticated": authentication_succeeded,
        "maximum_http_requests": plan.maximum_http_requests,
        "planned_workload_actions": len(plan.actions),
        "attempted_workload_actions": len(workload_results),
        "planned_cleanup_actions": len(plan.cleanup_actions),
        "attempted_cleanup_actions": len(cleanup_results),
        "workload_passed": workload_passed,
        "cleanup_actions_complete": cleanup_actions_complete,
        "isolated_database_teardown_required": True,
        "test_records_removed_claim": False,
        "canonical_data_unchanged": canonical_data_unchanged,
        "invariants_passed": bool(invariant_results)
        and all(result.passed for result in invariant_results),
        "idempotent_replays_passed": bool(replay_results)
        and all(result.replay_consistent for result in replay_results),
        "optimistic_concurrency_checked": any(
            result.operation == "optimistic_concurrency_probe" and result.passed
            for result in workload_results
        ),
        "overall_passed": (
            workload_passed
            and cleanup_actions_complete
            and canonical_data_unchanged
            and bool(invariant_results)
            and all(result.passed for result in invariant_results)
            and bool(replay_results)
            and all(result.replay_consistent for result in replay_results)
        ),
        "production_readiness_claim": False,
        "pilot_host_execution_claim": False,
        "result_interpretation": (
            "This summary covers only the named isolated test-database actions that were "
            "actually attempted. Cleanup actions do not erase append-only history; "
            "the isolated database still requires teardown. This is not a "
            "production-readiness or capacity claim."
        ),
        "workload_metrics": _result_metrics(workload_results, plan.actions),
        "cleanup_metrics": _result_metrics(cleanup_results, plan.cleanup_actions),
        "canonical_data_roots": [
            {
                "root_number": index,
                "before_file_count": before_fingerprints[index - 1]["file_count"],
                "after_file_count": after_fingerprints[index - 1]["file_count"],
                "unchanged": (before_fingerprints[index - 1] == after_fingerprints[index - 1]),
            }
            for index in range(1, len(before_fingerprints) + 1)
        ],
        "workload_actions": [result.as_dict() for result in workload_results],
        "cleanup_actions": [result.as_dict() for result in cleanup_results],
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"pm9-mutation-{plan.namespace}-{timestamp}.json"
    _write_report(report_path, report)
    return report, report_path


def _execute_action(
    *,
    client: httpx.Client,
    action: MutationAction,
    phase: Literal["workload", "cleanup"],
    headers: Mapping[str, str],
    context: dict[str, Any],
) -> _ActionResult:
    try:
        path = str(_substitute(action.path_template, context))
        _validated_request_path(path)
        body = _substitute(action.json_body_template, context)
    except KeyError:
        return _ActionResult(
            action_id=action.action_id,
            operation=action.operation,
            phase=phase,
            status_code=None,
            elapsed_ms=0.0,
            passed=False,
            assertion_count=len(action.assertions),
            assertions_passed=False,
            outcome="cleanup_uncertain_missing_fixture_context"
            if phase == "cleanup"
            else "missing_fixture_context",
        )

    request_headers = dict(headers)
    if action.idempotency_key is not None:
        request_headers["Idempotency-Key"] = action.idempotency_key
    started = time.perf_counter()
    try:
        response = client.request(
            action.method,
            path,
            headers=request_headers,
            json=body,
        )
    except httpx.HTTPError:
        return _ActionResult(
            action_id=action.action_id,
            operation=action.operation,
            phase=phase,
            status_code=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            passed=False,
            assertion_count=len(action.assertions),
            assertions_passed=False,
            outcome="transport_failure",
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response_payload = _safe_json(response)
    expected_status = response.status_code in action.expected_statuses
    assertions_passed = expected_status and _assertions_pass(
        action.assertions, response_payload, context
    )
    captures_passed = expected_status and _capture_values(
        action.captures, response_payload, context
    )
    replay_status: int | None = None
    replay_consistent: bool | None = None
    if action.replay and expected_status and assertions_passed and captures_passed:
        replay_started = time.perf_counter()
        try:
            replay_response = client.request(
                action.method,
                path,
                headers=request_headers,
                json=body,
            )
            elapsed_ms += (time.perf_counter() - replay_started) * 1000
            replay_status = replay_response.status_code
            replay_expected = action.replay_expected_statuses or action.expected_statuses
            replay_payload = _safe_json(replay_response)
            replay_consistent = (
                replay_status in replay_expected
                and replay_payload is not None
                and response_payload is not None
                and all(
                    _extract_json_path(replay_payload, json_path)
                    == _extract_json_path(response_payload, json_path)
                    for json_path in action.replay_match_paths
                )
            )
        except (httpx.HTTPError, KeyError, TypeError):
            replay_consistent = False
    passed = (
        expected_status and assertions_passed and captures_passed and replay_consistent is not False
    )
    return _ActionResult(
        action_id=action.action_id,
        operation=action.operation,
        phase=phase,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
        passed=passed,
        assertion_count=len(action.assertions),
        assertions_passed=assertions_passed,
        replay_status_code=replay_status,
        replay_consistent=replay_consistent,
        outcome="completed" if passed else "unexpected_result",
    )


def _login(client: httpx.Client, *, username: str, password: str) -> str:
    try:
        response = client.post(
            "/auth/login",
            json={"identifier": username, "password": password},
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("Mutation rehearsal authentication transport failed.") from exc
    if response.status_code != 200:
        raise RuntimeError("Mutation rehearsal authentication failed.")
    payload = _safe_json(response)
    token = payload.get("access_token") if isinstance(payload, Mapping) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("Mutation rehearsal authentication returned no access token.")
    return token


def _validate_test_database_url(database_url: str) -> str:
    try:
        parsed = make_url(database_url)
    except Exception as exc:  # noqa: BLE001 - never copy a credential-bearing URL
        raise ValueError("Mutation rehearsal requires a valid PostgreSQL test URL.") from exc
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Mutation rehearsal requires postgresql+psycopg://.")
    if not (parsed.database or "").endswith("_test"):
        raise ValueError("Mutation rehearsal database name must end with _test.")
    if not parsed.host or not parsed.username:
        raise ValueError("Mutation rehearsal database URL requires a host and username.")
    return hashlib.sha256(f"pm9-test-database:{parsed.database}".encode("utf-8")).hexdigest()


def _verify_test_target(
    client: httpx.Client,
    *,
    expected_database_fingerprint: str,
) -> None:
    """Fail before authentication unless the API attests to the same `_test` database."""

    try:
        response = client.get("/health/live")
    except httpx.HTTPError as exc:
        raise RuntimeError("Mutation rehearsal target attestation failed.") from exc
    payload = _safe_json(response)
    fingerprint = (
        payload.get("test_database_fingerprint")
        if response.status_code == 200 and isinstance(payload, Mapping)
        else None
    )
    if not isinstance(fingerprint, str) or not hmac.compare_digest(
        fingerprint,
        expected_database_fingerprint,
    ):
        raise RuntimeError(
            "Mutation rehearsal target is not attested to the supplied _test database."
        )


def _validate_operation_contract(
    *,
    operation: str,
    method: str,
    path_template: str,
    expected_statuses: Sequence[int],
) -> None:
    expected_method, patterns = _OPERATION_CONTRACTS[operation]
    path = urlsplit(path_template).path
    if method != expected_method or not any(pattern.fullmatch(path) for pattern in patterns):
        raise ValueError(f"Operation {operation} is not bound to the supplied method and route.")
    if operation == "optimistic_concurrency_probe" and tuple(expected_statuses) != (409,):
        raise ValueError("Optimistic-concurrency probes must require exactly HTTP 409.")
    if operation in _INVARIANT_OPERATIONS and tuple(expected_statuses) != (200,):
        raise ValueError("Invariant checks must require exactly HTTP 200.")


def _substitute(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        exact = _PLACEHOLDER_PATTERN.fullmatch(value)
        if exact:
            return context[exact.group(1)]

        def replace(match: re.Match[str]) -> str:
            return str(context[match.group(1)])

        return _PLACEHOLDER_PATTERN.sub(replace, value)
    if isinstance(value, Mapping):
        return {str(key): _substitute(item, context) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_substitute(item, context) for item in value)
    if isinstance(value, list):
        return [_substitute(item, context) for item in value]
    return value


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _capture_values(
    captures: Mapping[str, str],
    payload: Any,
    context: dict[str, Any],
) -> bool:
    try:
        captured = {
            name: _extract_json_path(payload, json_path) for name, json_path in captures.items()
        }
    except (KeyError, IndexError, TypeError):
        return False
    if any(isinstance(value, (dict, list, tuple)) or value is None for value in captured.values()):
        return False
    context.update(captured)
    return True


def _assertions_pass(
    assertions: Sequence[ResponseAssertion],
    payload: Any,
    context: Mapping[str, Any],
) -> bool:
    try:
        for assertion in assertions:
            actual = _extract_json_path(payload, assertion.json_path)
            expected = _substitute(assertion.expected, context)
            if assertion.operator == "eq" and actual != expected:
                return False
            if assertion.operator in {"gte", "lte"}:
                actual_number = Decimal(str(actual))
                expected_number = Decimal(str(expected))
                if assertion.operator == "gte" and actual_number < expected_number:
                    return False
                if assertion.operator == "lte" and actual_number > expected_number:
                    return False
            if assertion.operator == "length_eq" and len(actual) != int(expected):
                return False
            if assertion.operator == "unique":
                if not isinstance(actual, list):
                    return False
                projected = (
                    [_extract_json_path(item, expected) for item in actual]
                    if expected is not None
                    else actual
                )
                if len(projected) != len({str(item) for item in projected}):
                    return False
            if assertion.operator == "is_true" and actual is not True:
                return False
    except (
        InvalidOperation,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):
        return False
    return True


def _extract_json_path(payload: Any, json_path: str) -> Any:
    current = payload
    for component in json_path.split("."):
        if isinstance(current, Mapping):
            current = current[component]
        elif isinstance(current, list):
            current = current[int(component)]
        else:
            raise TypeError("JSON path traversed a scalar value.")
    return current


def _fingerprint_roots(roots: Sequence[Path]) -> tuple[dict[str, Any], ...]:
    return tuple(_fingerprint_root(Path(root)) for root in roots)


def _fingerprint_root(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    digest = hashlib.sha256()
    if not resolved_root.exists():
        digest.update(b"missing")
        return {"file_count": 0, "digest": digest.hexdigest()}
    if not resolved_root.is_dir() or resolved_root.is_symlink():
        raise ValueError("Canonical data fingerprint roots must be real directories.")
    file_count = 0
    for path in sorted(resolved_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Canonical data fingerprint roots must not contain symlinks.")
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(resolved_root):
            raise ValueError("Canonical data fingerprint path escaped its configured root.")
        relative_path = resolved_path.relative_to(resolved_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        with resolved_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
        file_count += 1
    return {"file_count": file_count, "digest": digest.hexdigest()}


def _parse_action_list(value: Any, label: str) -> tuple[MutationAction, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Mutation plan {label} must be a JSON list.")
    return tuple(_parse_action(item) for item in value)


def _parse_action(value: Any) -> MutationAction:
    if not isinstance(value, Mapping):
        raise ValueError("Every mutation action must be a JSON object.")
    allowed = {
        "action_id",
        "operation",
        "method",
        "path_template",
        "expected_statuses",
        "json_body_template",
        "idempotency_key",
        "captures",
        "assertions",
        "replay",
        "replay_expected_statuses",
        "replay_match_paths",
    }
    required = {
        "action_id",
        "operation",
        "method",
        "path_template",
        "expected_statuses",
    }
    _require_exact_keys(value, allowed, "action", required=required)
    assertions_value = value.get("assertions", [])
    if not isinstance(assertions_value, list):
        raise ValueError("Mutation action assertions must be a JSON list.")
    assertions = tuple(_parse_assertion(item) for item in assertions_value)
    captures = value.get("captures", {})
    if not isinstance(captures, Mapping):
        raise ValueError("Mutation action captures must be a JSON object.")
    body = value.get("json_body_template")
    if body is not None and not isinstance(body, Mapping):
        raise ValueError("Mutation action JSON bodies must be objects.")
    return MutationAction(
        action_id=str(value["action_id"]),
        operation=str(value["operation"]),
        method=str(value["method"]),
        path_template=str(value["path_template"]),
        expected_statuses=_status_tuple(value["expected_statuses"]),
        json_body_template=body,
        idempotency_key=(
            str(value["idempotency_key"]) if value.get("idempotency_key") is not None else None
        ),
        captures={str(key): str(item) for key, item in captures.items()},
        assertions=assertions,
        replay=value.get("replay", False) is True,
        replay_expected_statuses=(
            _status_tuple(value["replay_expected_statuses"])
            if value.get("replay_expected_statuses") is not None
            else None
        ),
        replay_match_paths=tuple(str(item) for item in value.get("replay_match_paths", [])),
    )


def _parse_assertion(value: Any) -> ResponseAssertion:
    if not isinstance(value, Mapping):
        raise ValueError("Every response assertion must be a JSON object.")
    _require_exact_keys(
        value,
        {"json_path", "operator", "expected"},
        "assertion",
        required={"json_path", "operator"},
    )
    return ResponseAssertion(
        json_path=str(value["json_path"]),
        operator=str(value["operator"]),  # type: ignore[arg-type]
        expected=value.get("expected"),
    )


def _status_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError("Expected statuses must be a JSON list.")
    return tuple(int(item) for item in value)


def _require_exact_keys(
    value: Mapping[str, Any],
    allowed: set[str],
    label: str,
    *,
    required: set[str] | None = None,
) -> None:
    keys = {str(key) for key in value}
    unknown = keys - allowed
    missing = (required or allowed) - keys
    if unknown:
        raise ValueError(f"Mutation {label} contains unsupported fields.")
    if missing:
        raise ValueError(f"Mutation {label} is missing required fields.")


def _reject_secret_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(fragment in normalized_key for fragment in _FORBIDDEN_PLAN_KEY_FRAGMENTS):
                raise ValueError("Mutation plans must not contain credential-bearing fields.")
            _reject_secret_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_fields(item)


def _result_metrics(
    results: Sequence[_ActionResult],
    planned_actions: Sequence[MutationAction],
) -> dict[str, Any]:
    methods = {action.action_id: action.method for action in planned_actions}
    mutation_results = [
        result for result in results if methods.get(result.action_id) in _MUTATING_METHODS
    ]
    conflict_results = [
        result for result in results if result.operation == "optimistic_concurrency_probe"
    ]
    latencies = sorted(result.elapsed_ms for result in results)
    unexpected_failures = sum(1 for result in results if not result.passed)
    return {
        "attempted_count": len(results),
        "passed_count": sum(1 for result in results if result.passed),
        "unexpected_failure_count": unexpected_failures,
        "unexpected_failure_rate": round(unexpected_failures / len(results), 6) if results else 0.0,
        "mutation_attempted_count": len(mutation_results),
        "mutation_success_rate": round(
            sum(1 for result in mutation_results if result.passed) / len(mutation_results),
            6,
        )
        if mutation_results
        else 0.0,
        "expected_conflict_attempted_count": len(conflict_results),
        "expected_conflict_observed_count": sum(1 for result in conflict_results if result.passed),
        "idempotent_replay_count": sum(
            1 for result in results if result.replay_consistent is not None
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "max": round(latencies[-1], 3) if latencies else 0.0,
        },
    }


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    rank = max(0, math.ceil((percentile / 100) * len(values)) - 1)
    return round(values[rank], 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--database-url-env", default="TEST_DATABASE_URL")
    parser.add_argument("--password-env", default="PM9_TEST_PASSWORD")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--canonical-data-root",
        type=Path,
        action="append",
        dest="canonical_data_roots",
    )
    args = parser.parse_args()
    database_url = os.getenv(args.database_url_env)
    password = os.getenv(args.password_env)
    if not database_url:
        raise RuntimeError(
            f"{args.database_url_env} must provide the isolated PostgreSQL test URL."
        )
    if not password:
        raise RuntimeError(f"{args.password_env} must provide the test password.")
    report, report_path = run_mutation_rehearsal(
        plan=load_mutation_plan(args.plan),
        database_url=database_url,
        base_url=args.base_url,
        username=args.username,
        password=password,
        output_dir=args.output_dir,
        canonical_data_roots=(
            tuple(args.canonical_data_roots) if args.canonical_data_roots else _CANONICAL_DATA_ROOTS
        ),
    )
    print(
        "PM9 isolated mutation rehearsal: "
        f"passed={report['overall_passed']} "
        f"cleanup_actions_complete={report['cleanup_actions_complete']} "
        f"database_teardown_required={report['isolated_database_teardown_required']} "
        f"report={report_path}; not a production-readiness claim."
    )


if __name__ == "__main__":
    main()
