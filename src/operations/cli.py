"""Explicit operator commands for durable PM7 background operations."""

from __future__ import annotations

import argparse
import json
import sys
from uuid import UUID, uuid4

from src.config.settings import get_settings
from src.operations.service import build_operations_service
from src.security.audit import AuditContext
from src.security.cli_context import load_cli_actor


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Inspect and control supported PM7 background jobs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--actor-username", default="admin.demo")

    trigger = subparsers.add_parser("trigger")
    trigger.add_argument("job_key")
    trigger.add_argument("--idempotency-key", required=True)
    trigger.add_argument("--actor-username", default="admin.demo")

    state = subparsers.add_parser("set-enabled")
    state.add_argument("job_key")
    state.add_argument("--enabled", choices=("true", "false"), required=True)
    state.add_argument("--expected-version", type=int, required=True)
    state.add_argument("--actor-username", default="admin.demo")

    retry = subparsers.add_parser("retry")
    retry.add_argument("execution_id", type=UUID)
    retry.add_argument("--idempotency-key", required=True)
    retry.add_argument("--actor-username", default="admin.demo")

    outbox_retry = subparsers.add_parser("retry-outbox")
    outbox_retry.add_argument("event_id", type=UUID)
    outbox_retry.add_argument("--idempotency-key", required=True)
    outbox_retry.add_argument("--actor-username", default="admin.demo")

    alerts = subparsers.add_parser("evaluate-alerts")
    alerts.add_argument("--actor-username", default="admin.demo")

    args = parser.parse_args()
    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise SystemExit("Operations CLI requires STORAGE_BACKEND=postgresql.")
    service = build_operations_service()

    if args.command == "status":
        actor = load_cli_actor(args.actor_username)
        payload = {
            "jobs": service.list_jobs(actor=actor),
            "metrics": service.metrics(actor=actor),
            "worker": service.worker_health(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    actor = load_cli_actor(args.actor_username)
    context = AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=f"cli-{args.command}-{uuid4()}",
    )
    if args.command == "trigger":
        result = service.trigger_job(
            args.job_key,
            idempotency_key=args.idempotency_key,
            actor=actor,
            audit_context=context,
        )
    elif args.command == "set-enabled":
        result = service.set_job_enabled(
            args.job_key,
            enabled=args.enabled == "true",
            expected_version=args.expected_version,
            actor=actor,
            audit_context=context,
        )
    elif args.command == "retry":
        result = service.retry_execution(
            args.execution_id,
            idempotency_key=args.idempotency_key,
            actor=actor,
            audit_context=context,
        )
    elif args.command == "retry-outbox":
        result = service.redrive_outbox_event(
            args.event_id,
            idempotency_key=args.idempotency_key,
            actor=actor,
            audit_context=context,
        )
    else:
        result = service.evaluate_operational_alerts(actor=actor)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
