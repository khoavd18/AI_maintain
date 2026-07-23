"""Explicit CLI for initial administrator and development demo identities."""

import argparse
from getpass import getpass
import os

from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.security.permissions import Role
from src.security.service import AuthService, DuplicateUserError

DEMO_USERS = (
    ("admin.demo", "Quản trị viên demo", Role.ADMINISTRATOR, None),
    ("manager.demo", "Quản lý cơ sở demo", Role.PROPERTY_MANAGER, None),
    ("engineer.demo", "Kỹ sư trưởng demo", Role.CHIEF_ENGINEER, None),
    ("technician.demo", "Kỹ thuật viên demo", Role.TECHNICIAN, "TECH_002"),
    ("helpdesk.demo", "Tiếp nhận demo", Role.HELPDESK, None),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin = subparsers.add_parser("create-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name", required=True)
    admin.add_argument("--email")
    subparsers.add_parser("seed-demo-users")
    args = parser.parse_args()

    settings = get_settings()
    service = AuthService(get_session_factory(settings.database_url), settings)
    if args.command == "create-admin":
        password = _password_from_environment_or_prompt("ADMIN_BOOTSTRAP_PASSWORD")
        try:
            user = service.bootstrap_user(
                username=args.username,
                email=args.email,
                password=password,
                display_name=args.display_name,
                role=Role.ADMINISTRATOR,
            )
        except DuplicateUserError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Created administrator: {user['username']}")
        return

    if settings.app_environment != "development":
        raise SystemExit("seed-demo-users is allowed only when APP_ENVIRONMENT=development")
    password = _password_from_environment_or_prompt("DEMO_USER_PASSWORD")
    created = 0
    for username, display_name, role, technician_id in DEMO_USERS:
        try:
            service.bootstrap_user(
                username=username,
                email=None,
                password=password,
                display_name=display_name,
                role=role,
                technician_id=technician_id,
            )
            created += 1
        except DuplicateUserError:
            print(f"Skipped existing demo user: {username}")
    print(f"Created {created} explicit development demo user(s).")


def _password_from_environment_or_prompt(variable: str) -> str:
    value = os.getenv(variable)
    if value:
        return value
    first = getpass("Password: ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    return first


if __name__ == "__main__":
    main()
