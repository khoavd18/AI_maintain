"""Explicit CLI for ticket/SLA reference seeding and escalation evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from src.config.settings import get_settings
from src.database.models import User
from src.database.session import get_session_factory
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser
from src.ticket_management.service import build_ticket_workflow_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed-defaults")
    seed.add_argument("--actor-username", default="admin.demo")

    evaluate = subparsers.add_parser("evaluate-escalations")
    evaluate.add_argument("--actor-username", default="manager.demo")
    evaluate.add_argument("--as-of", type=datetime.fromisoformat, default=None)
    evaluate.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise SystemExit("Ticket operations CLI requires STORAGE_BACKEND=postgresql.")
    actor = _load_actor(args.actor_username)
    service = build_ticket_workflow_service()
    context = AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=f"cli-ticketing-{args.command}",
    )
    if args.command == "seed-defaults":
        counts = service.seed_defaults(actor=actor, audit_context=context)
        print(", ".join(f"{name}={count}" for name, count in counts.items()))
        return

    report = service.evaluate_escalations(
        dry_run=args.dry_run,
        actor=actor,
        audit_context=context,
        as_of=args.as_of,
    )
    print(f"Dry run: {str(report['dry_run']).lower()}")
    print(f"Candidates: {report['candidate_count']}")
    print(f"Created: {report['created_count']}")
    for item in report["candidates"]:
        print(f"- {item['ticket_id']}: {item['rule_code']}")


def _load_actor(username: str) -> CurrentUser:
    settings = get_settings()
    with get_session_factory(settings.database_url)() as session:
        user = session.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None or not user.is_active:
            raise SystemExit(f"Active user not found: {username}")
        now = datetime.now(timezone.utc)
        return CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=Role(user.role),
            permissions=permissions_for_role(user.role),
            technician_id=user.technician_id,
            is_active=user.is_active,
            version=user.version,
            session_id=uuid4(),
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at or now,
        )


if __name__ == "__main__":
    main()
