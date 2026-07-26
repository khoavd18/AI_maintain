"""PostgreSQL-backed authentication, authorization, and audit coverage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import ProgrammingError

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import ProcessedDataService
from src.config.settings import Settings
from src.database.models import Asset, AuditLog, Ticket, User
from src.database.session import get_session_factory
from src.repositories.contracts import IntegrityViolationError
from src.repositories.postgres import PostgresMaintenanceRepository
from src.security.audit import AuditContext
from src.security.dependencies import get_auth_service
from src.security.passwords import hash_password, verify_password
from src.security.permissions import Permission, ROLE_PERMISSIONS, Role
from src.security.service import AuthenticationError, AuthService
from src.security.tokens import InvalidAccessTokenError, create_access_token, decode_access_token

TEST_PASSWORD = "Internal-Test-Password-42!"
NEW_TEST_PASSWORD = "Changed-Internal-Test-Password-84!"


@pytest.fixture
def auth_system(clean_postgres_database: str) -> dict[str, Any]:
    settings = Settings(
        app_environment="test",
        database_url=clean_postgres_database,
        token_signing_secret="test-only-signing-secret-with-more-than-32-characters",
        access_token_lifetime_minutes=15,
        refresh_session_lifetime_days=7,
    )
    session_factory = get_session_factory(clean_postgres_database)
    auth_service = AuthService(session_factory, settings)
    repository = PostgresMaintenanceRepository(session_factory)
    today = date.today()
    with session_factory() as session, session.begin():
        session.add(
            Asset(
                asset_id="GENERATOR_002",
                asset_name="Máy phát điện dự phòng 002",
                asset_type="generator",
                location="Sân thượng phía Đông",
                criticality="critical",
                status="warning",
                installation_date=date(2023, 1, 1),
                last_maintenance_date=today - timedelta(days=30),
                maintenance_interval_days=30,
                next_maintenance_date=today,
            )
        )

    users = {
        Role.ADMINISTRATOR: auth_service.bootstrap_user(
            username="admin.test",
            email="admin.test@example.invalid",
            password=TEST_PASSWORD,
            display_name="Quản trị viên test",
            role=Role.ADMINISTRATOR,
        ),
        Role.PROPERTY_MANAGER: auth_service.bootstrap_user(
            username="manager.test",
            email=None,
            password=TEST_PASSWORD,
            display_name="Quản lý test",
            role=Role.PROPERTY_MANAGER,
        ),
        Role.CHIEF_ENGINEER: auth_service.bootstrap_user(
            username="engineer.test",
            email=None,
            password=TEST_PASSWORD,
            display_name="Kỹ sư trưởng test",
            role=Role.CHIEF_ENGINEER,
        ),
        Role.TECHNICIAN: auth_service.bootstrap_user(
            username="technician.test",
            email=None,
            password=TEST_PASSWORD,
            display_name="Kỹ thuật viên test",
            role=Role.TECHNICIAN,
            technician_id="TECH_002",
        ),
        Role.HELPDESK: auth_service.bootstrap_user(
            username="helpdesk.test",
            email=None,
            password=TEST_PASSWORD,
            display_name="Helpdesk test",
            role=Role.HELPDESK,
        ),
        Role.STOREKEEPER: auth_service.bootstrap_user(
            username="storekeeper.test",
            email=None,
            password=TEST_PASSWORD,
            display_name="Thủ kho test",
            role=Role.STOREKEEPER,
        ),
    }
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[_service] = lambda: ProcessedDataService(repository=repository)
    client = TestClient(app)
    return {
        "app": app,
        "client": client,
        "auth": auth_service,
        "repository": repository,
        "session_factory": session_factory,
        "users": users,
        "today": today,
    }


def test_password_hashing_uses_argon2_and_rejects_wrong_password() -> None:
    password_hash = hash_password(TEST_PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert TEST_PASSWORD not in password_hash
    assert verify_password(TEST_PASSWORD, password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password(TEST_PASSWORD, "malformed-hash")


@pytest.mark.postgres
def test_login_is_generic_for_wrong_unknown_and_inactive_accounts(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    successful = _login(client, "ADMIN.TEST")
    assert successful.status_code == 200
    assert successful.json()["user"]["role"] == "administrator"
    assert "password_hash" not in successful.text
    assert client.cookies.get("maintenance_refresh")

    wrong = client.post(
        "/auth/login",
        json={"identifier": "admin.test", "password": "wrong-password"},
    )
    unknown = client.post(
        "/auth/login",
        json={"identifier": "unknown.test", "password": "wrong-password"},
    )
    with auth_system["session_factory"]() as session, session.begin():
        user = session.scalar(select(User).where(User.username == "helpdesk.test"))
        user.is_active = False
    inactive = _login(client, "helpdesk.test")

    assert wrong.status_code == unknown.status_code == inactive.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == inactive.json()["detail"]


def test_role_permission_matrix_is_explicit_and_least_privilege() -> None:
    assert ROLE_PERMISSIONS[Role.ADMINISTRATOR] == frozenset(Permission)
    assert Permission.AUDIT_LOGS_READ in ROLE_PERMISSIONS[Role.PROPERTY_MANAGER]
    assert Permission.MAINTENANCE_LOGS_CREATE not in ROLE_PERMISSIONS[Role.PROPERTY_MANAGER]
    assert Permission.TICKETS_ASSIGN not in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.MAINTENANCE_LOGS_CREATE in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.TICKETS_CREATE in ROLE_PERMISSIONS[Role.HELPDESK]
    assert Permission.TICKETS_RESOLVE not in ROLE_PERMISSIONS[Role.HELPDESK]
    assert ROLE_PERMISSIONS[Role.STOREKEEPER] == frozenset(
        {
            Permission.ASSETS_READ,
            Permission.TICKETS_READ,
            Permission.WORK_ORDERS_READ,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_PARTS_MANAGE,
            Permission.INVENTORY_LOCATIONS_MANAGE,
            Permission.INVENTORY_RECEIVE,
            Permission.INVENTORY_RESERVE,
            Permission.INVENTORY_ISSUE,
            Permission.INVENTORY_RETURN,
            Permission.INVENTORY_TRANSFER,
            Permission.INVENTORY_ADJUST,
            Permission.WORK_ORDER_PARTS_READ,
            Permission.INVENTORY_ATTACHMENTS_READ,
            Permission.INVENTORY_ATTACHMENTS_CREATE,
            Permission.INVENTORY_ATTACHMENTS_DELETE,
            Permission.NOTIFICATIONS_READ,
        }
    )
    assert Permission.NOTIFICATIONS_READ in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.NOTIFICATIONS_READ in ROLE_PERMISSIONS[Role.HELPDESK]
    assert Permission.JOB_OPERATIONS_READ not in ROLE_PERMISSIONS[Role.PROPERTY_MANAGER]
    assert Permission.JOB_OPERATIONS_MANAGE not in ROLE_PERMISSIONS[Role.CHIEF_ENGINEER]


def test_expired_access_token_is_rejected() -> None:
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    token, _ = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        role=Role.ADMINISTRATOR.value,
        user_version=1,
        signing_secret="test-only-signing-secret-with-more-than-32-characters",
        lifetime_minutes=1,
        now=now,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(
            token,
            "test-only-signing-secret-with-more-than-32-characters",
        )


@pytest.mark.postgres
def test_protected_reads_reject_missing_invalid_and_insufficient_tokens(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    assert client.get("/health").status_code == 200
    assert client.get("/assets").status_code == 401
    assert client.get("/assets", headers={"Authorization": "Bearer invalid"}).status_code == 401

    storekeeper = _login_headers(client, "storekeeper.test")
    assert client.get("/assets", headers=storekeeper).status_code == 200
    assert client.get("/tickets", headers=storekeeper).status_code == 200
    denied = client.get("/audit-logs", headers=storekeeper)
    assert denied.status_code == 403


@pytest.mark.postgres
def test_refresh_rotation_logout_and_password_change_revoke_sessions(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    auth_service: AuthService = auth_system["auth"]
    login = _login(client, "manager.test")
    old_access = login.json()["access_token"]
    old_refresh = client.cookies.get("maintenance_refresh")
    old_csrf = client.cookies.get("maintenance_csrf")

    refreshed = client.post("/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert refreshed.status_code == 200
    assert client.cookies.get("maintenance_refresh") != old_refresh
    with pytest.raises(AuthenticationError):
        auth_service.refresh(
            refresh_token=old_refresh,
            csrf_token=old_csrf,
            user_agent="pytest",
            request_id="replay-test",
        )

    current_access = refreshed.json()["access_token"]
    logout = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": client.cookies.get("maintenance_csrf")},
    )
    assert logout.status_code == 204
    assert client.get("/auth/me", headers=_headers(current_access)).status_code == 401
    assert client.get("/auth/me", headers=_headers(old_access)).status_code == 401

    login_again = _login(client, "manager.test")
    changed = client.post(
        "/auth/change-password",
        headers=_headers(login_again.json()["access_token"]),
        json={"current_password": TEST_PASSWORD, "new_password": NEW_TEST_PASSWORD},
    )
    assert changed.status_code == 204
    assert client.get(
        "/auth/me", headers=_headers(login_again.json()["access_token"])
    ).status_code == 401
    assert _login(client, "manager.test", NEW_TEST_PASSWORD).status_code == 200


@pytest.mark.postgres
def test_concurrent_refresh_allows_only_one_rotation(auth_system: dict[str, Any]) -> None:
    auth_service: AuthService = auth_system["auth"]
    result = auth_service.login(
        identifier="engineer.test",
        password=TEST_PASSWORD,
        user_agent="pytest",
        request_id="concurrent-login",
    )

    def rotate(index: int) -> bool:
        try:
            auth_service.refresh(
                refresh_token=result.refresh_token,
                csrf_token=result.csrf_token,
                user_agent="pytest",
                request_id=f"concurrent-refresh-{index}",
            )
            return True
        except AuthenticationError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(rotate, range(2)))

    assert sorted(outcomes) == [False, True]


@pytest.mark.postgres
def test_login_rate_limit_keeps_generic_response(auth_system: dict[str, Any]) -> None:
    client: TestClient = auth_system["client"]
    responses = [
        client.post(
            "/auth/login",
            json={"identifier": "storekeeper.test", "password": "wrong-password"},
        )
        for _ in range(7)
    ]
    assert {response.status_code for response in responses} == {401}
    assert {response.json()["detail"] for response in responses} == {
        "Thông tin đăng nhập không hợp lệ."
    }


@pytest.mark.postgres
def test_administrator_user_management_revokes_deactivated_user(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    admin = _login_headers(client, "admin.test")
    created = client.post(
        "/users",
        headers=admin,
        json={
            "username": "new.user",
            "email": "new.user@example.invalid",
            "password": TEST_PASSWORD,
            "display_name": "Người dùng mới",
            "role": "helpdesk",
            "technician_id": None,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    assert "password" not in created.text
    user_access = _login(client, "new.user").json()["access_token"]

    updated = client.patch(
        f"/users/{created.json()['id']}",
        headers=admin,
        json={"role": "property_manager", "is_active": False},
    )
    assert updated.status_code == 200
    assert not updated.json()["is_active"]
    assert client.get("/auth/me", headers=_headers(user_access)).status_code == 401
    users = client.get("/users", headers=admin)
    assert users.status_code == 200
    assert all("password_hash" not in row for row in users.json())


@pytest.mark.postgres
def test_helpdesk_and_technician_resource_rules_are_enforced(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    helpdesk = _login_headers(client, "helpdesk.test")
    assigned_attempt = client.post(
        "/tickets",
        headers=helpdesk,
        json=_ticket_payload(technician_id="TECH_002"),
    )
    assert assigned_attempt.status_code == 201
    unassigned = client.post(
        "/tickets",
        headers=helpdesk,
        json=_ticket_payload(technician_id="UNASSIGNED"),
    )
    assert unassigned.status_code == 201
    assert client.patch(
        f"/tickets/{unassigned.json()['ticket_id']}",
        headers=helpdesk,
        json={"status": "Đang xử lý"},
    ).status_code == 403
    assert client.post(
        "/maintenance/logs",
        headers=helpdesk,
        json=_log_payload(unassigned.json()["ticket_id"], auth_system["today"]),
    ).status_code == 403

    engineer = _login_headers(client, "engineer.test")
    assigned = client.post(
        "/tickets", headers=engineer, json=_ticket_payload(technician_id="TECH_002")
    ).json()
    client.patch(
        f"/tickets/{assigned['ticket_id']}",
        headers=engineer,
        json={"status": "Đang xử lý"},
    )
    technician = _login_headers(client, "technician.test")
    visible = client.get("/tickets", headers=technician).json()
    assert {ticket["ticket_id"] for ticket in visible} == {
        assigned_attempt.json()["ticket_id"],
        assigned["ticket_id"],
    }
    assert client.patch(
        f"/tickets/{assigned['ticket_id']}",
        headers=technician,
        json={"technician_id": "TECH_999"},
    ).status_code == 403
    log = client.post(
        "/maintenance/logs",
        headers=technician,
        json=_log_payload(assigned["ticket_id"], auth_system["today"]),
    )
    assert log.status_code == 201
    assert client.patch(
        f"/tickets/{assigned['ticket_id']}",
        headers=technician,
        json={"status": "Đã xử lý"},
    ).status_code == 200


@pytest.mark.postgres
def test_audit_events_are_redacted_paginated_and_immutable(
    auth_system: dict[str, Any],
) -> None:
    client: TestClient = auth_system["client"]
    admin = _login_headers(client, "admin.test")
    created = client.post(
        "/tickets",
        headers=admin,
        json=_ticket_payload(technician_id="TECH_002"),
    )
    assert created.status_code == 201
    page = client.get(
        "/audit-logs",
        headers=admin,
        params={"action": "ticket.created", "page": 1, "page_size": 10},
    )
    assert page.status_code == 200
    event = page.json()["items"][0]
    serialized = str(event).lower()
    assert "issue_description" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert event["request_id"]

    with auth_system["session_factory"]() as session:
        audit_id = session.scalar(select(AuditLog.id).limit(1))
    with pytest.raises(ProgrammingError):
        with auth_system["session_factory"]() as session, session.begin():
            session.execute(
                update(AuditLog).where(AuditLog.id == audit_id).values(outcome="changed")
            )


@pytest.mark.postgres
def test_audit_failure_rolls_back_business_write(auth_system: dict[str, Any]) -> None:
    repository: PostgresMaintenanceRepository = auth_system["repository"]
    session_factory = auth_system["session_factory"]
    before = _ticket_count(session_factory)
    with pytest.raises(IntegrityViolationError):
        repository.create_ticket(
            {
                "asset_id": "GENERATOR_002",
                "issue_description": "Không được commit nếu audit actor không tồn tại.",
                "priority": "Cao",
                "status": "Mới tạo",
                "failure_category": "Lỗi điện",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "resolved_at": None,
                "technician_id": "TECH_002",
                "manager_note": None,
                "note": None,
            },
            audit_context=AuditContext(
                actor_user_id=uuid4(),
                actor_display_name="Unknown actor",
                request_id="rollback-test",
            ),
        )
    assert _ticket_count(session_factory) == before


def _login(
    client: TestClient,
    identifier: str,
    password: str = TEST_PASSWORD,
):
    return client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )


def _login_headers(client: TestClient, identifier: str) -> dict[str, str]:
    response = _login(client, identifier)
    assert response.status_code == 200, response.text
    return _headers(response.json()["access_token"])


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _ticket_payload(*, technician_id: str) -> dict[str, object]:
    return {
        "asset_id": "GENERATOR_002",
        "issue_description": "Kiểm tra cảnh báo điện và khả năng khởi động thiết bị.",
        "priority": "Cao",
        "failure_category": "Lỗi điện",
        "technician_id": technician_id,
        "manager_note": "Chỉ dùng cho test nội bộ.",
    }


def _log_payload(ticket_id: str, maintenance_date: date) -> dict[str, object]:
    return {
        "ticket_id": ticket_id,
        "asset_id": "GENERATOR_002",
        "maintenance_date": maintenance_date.isoformat(),
        "inspection_result": "Đã kiểm tra tải và đầu nối.",
        "actions_taken": "Siết đầu nối và chạy thử có tải.",
        "parts_replaced": None,
        "technician_note": "Thông số ổn định sau kiểm tra.",
        "maintenance_result": "Đã xử lý",
        "follow_up_required": False,
        "next_maintenance_date": (maintenance_date + timedelta(days=30)).isoformat(),
    }


def _ticket_count(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(Ticket)) or 0)
