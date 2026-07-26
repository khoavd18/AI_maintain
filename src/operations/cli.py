"""Explicit operator commands for durable PM7 background operations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from src.config.settings import get_settings
from src.database.models import User
from src.database.session import get_session_factory
from src.operations.service import build_operations_service
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser


def main() -> None:
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

    args = parser.parse_args()
    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise SystemExit("Operations CLI requires STORAGE_BACKEND=postgresql.")
    service = build_operations_service()

    if args.command == "status":
        actor = _load_actor(args.actor_username)
        payload = {
            "jobs": service.list_jobs(actor=actor),
            "metrics": service.metrics(actor=actor),
            "worker": service.worker_health(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    actor = _load_actor(args.actor_username)
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
    else:
        result = service.retry_execution(
            args.execution_id,
            idempotency_key=args.idempotency_key,
            actor=actor,
            audit_context=context,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _load_actor(username: str) -> CurrentUser:
    settings = get_settings()
    with get_session_factory(settings.database_url)() as session:
        user = session.scalar(
            select(User).where(User.username == username.strip().lower())
        )
        if user is None or not user.is_active:
            raise SystemExit(f"Active user not found: {username}")
        role = Role(user.role)
        return CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=role,
            permissions=permissions_for_role(role),
            technician_id=user.technician_id,
            is_active=user.is_active,
            version=user.version,
            session_id=uuid4(),
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at or datetime.now(timezone.utc),
        )


if __name__ == "__main__":
    main()
