"""Explicit CLI for ticket/SLA reference seeding and escalation evaluation."""

from __future__ import annotations

import argparse
from datetime import datetime

from src.config.settings import get_settings
from src.security.audit import AuditContext
from src.security.cli_context import load_cli_actor
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
    actor = load_cli_actor(args.actor_username)
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


if __name__ == "__main__":
    main()
