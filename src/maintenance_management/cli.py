"""Explicit administrative commands for maintenance planning."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.config.settings import get_settings
from src.database.models import User
from src.database.session import get_session_factory
from src.maintenance_management.service import build_maintenance_planning_service
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preventive maintenance planning administration."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--as-of", type=date.fromisoformat, default=None)
    generate.add_argument("--plan-id", type=UUID, default=None)
    generate.add_argument("--dry-run", action="store_true")
    generate.add_argument("--actor-username", default="engineer.demo")

    seed = subparsers.add_parser("seed-development")
    seed.add_argument("--actor-username", default="engineer.demo")
    seed.add_argument("--technician-username", default="technician.demo")
    seed.add_argument("--generate", action="store_true")

    args = parser.parse_args()
    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise SystemExit("Maintenance planning CLI requires STORAGE_BACKEND=postgresql.")
    service = build_maintenance_planning_service()
    actor = _load_actor(args.actor_username)
    context = AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=f"cli-{args.command}",
    )
    if args.command == "generate":
        as_of = args.as_of or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        report = service.generate(
            as_of_date=as_of,
            plan_id=args.plan_id,
            dry_run=args.dry_run,
            actor=actor,
            audit_context=context,
        )
        _print_generation_report(report)
        return

    if settings.app_environment not in {"development", "test"}:
        raise SystemExit("seed-development is allowed only in development/test.")
    technician = _load_actor(args.technician_username)
    if technician.role is not Role.TECHNICIAN:
        raise SystemExit("--technician-username must identify an active technician.")
    created_templates, created_plans = _seed_development(
        service, actor=actor, technician=technician, audit_context=context
    )
    print(f"Created checklist templates: {created_templates}")
    print(f"Created maintenance plans: {created_plans}")
    if args.generate:
        report = service.generate(
            as_of_date=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date(),
            plan_id=None,
            dry_run=False,
            actor=actor,
            audit_context=context,
        )
        _print_generation_report(report)


def _seed_development(
    service,
    *,
    actor: CurrentUser,
    technician: CurrentUser,
    audit_context: AuditContext,
) -> tuple[int, int]:
    template_specs = [
        (
            "CHK-HVAC-PM",
            "Checklist bảo trì HVAC",
            "hvac",
            "HVAC_001",
            "PM-HVAC-001",
            30,
        ),
        (
            "CHK-PUMP-PM",
            "Checklist bảo trì máy bơm",
            "pump",
            "PUMP_001",
            "PM-PUMP-001",
            8,
        ),
        (
            "CHK-GEN-PM",
            "Checklist bảo trì máy phát",
            "generator",
            "GENERATOR_002",
            "PM-GENERATOR-002",
            4,
        ),
    ]
    templates = service.list_templates(
        status=None, asset_type=None, search=None, page=1, page_size=200
    )["items"]
    by_code = {item["code"]: item for item in templates}
    created_templates = 0
    created_plans = 0
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    existing_plans = service.list_plans(
        asset_id=None,
        status=None,
        search=None,
        due_from=None,
        due_to=None,
        page=1,
        page_size=1000,
    )["items"]
    plan_codes = {item["plan_code"] for item in existing_plans}
    for template_code, name, asset_type, asset_id, plan_code, interval_days in template_specs:
        template = by_code.get(template_code)
        if template is None:
            template = service.create_template(
                {
                    "code": template_code,
                    "name": name,
                    "asset_type": asset_type,
                    "description": "Template development rõ safety-critical step.",
                    "items": _seed_items(),
                },
                actor=actor,
                audit_context=audit_context,
            )
            created_templates += 1
        if plan_code in plan_codes:
            continue
        service.create_plan(
            {
                "plan_code": plan_code,
                "name": name.replace("Checklist", "Kế hoạch"),
                "description": "Development seed; không tự động chạy khi API startup.",
                "asset_id": asset_id,
                "interval_value": interval_days,
                "interval_unit": "day",
                "start_date": today,
                    "end_date": today + timedelta(days=365),
                "local_timezone": "Asia/Ho_Chi_Minh",
                "lead_time_days": 7,
                "grace_period_days": 1,
                "estimated_duration_minutes": 90,
                "default_priority": "medium",
                "default_assignee_user_id": technician.id,
                "checklist_template_id": UUID(template["id"]),
                "instructions": "Xác nhận an toàn trước khi thực hiện checklist.",
                "recurrence_rule": None,
            },
            actor=actor,
            audit_context=audit_context,
        )
        created_plans += 1
    return created_templates, created_plans


def _seed_items() -> list[dict[str, object]]:
    return [
        {
            "sequence": 1,
            "instruction": "Xác nhận cô lập năng lượng và khu vực làm việc an toàn.",
            "response_type": "checkbox",
            "is_required": True,
            "safety_critical": True,
            "allow_not_applicable": False,
            "expected_unit": None,
            "minimum_value": None,
            "maximum_value": None,
            "guidance": "Dừng công việc nếu chưa đáp ứng điều kiện an toàn.",
        },
        {
            "sequence": 2,
            "instruction": "Kiểm tra trực quan và ghi nhận tình trạng thiết bị.",
            "response_type": "pass_fail",
            "is_required": True,
            "safety_critical": False,
            "allow_not_applicable": False,
            "expected_unit": None,
            "minimum_value": None,
            "maximum_value": None,
            "guidance": None,
        },
    ]


def _load_actor(username: str) -> CurrentUser:
    settings = get_settings()
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
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


def _print_generation_report(report: dict[str, object]) -> None:
    print(f"Dry run: {str(report['dry_run']).lower()}")
    print(f"As of date: {report['as_of_date']}")
    print(f"Generated: {report['generated_count']}")
    print(f"Would generate: {report['would_generate_count']}")
    print(f"Skipped: {report['skipped_count']}")


if __name__ == "__main__":
    main()
