"""Asset lifecycle, hierarchy, attachment, QR, audit, and RBAC integration tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import ProcessedDataService
from src.asset_management.service import AssetManagementService
from src.asset_management.storage import AttachmentStorageError, LocalAttachmentStorage
from src.database.models import AuditLog
from src.database.session import get_session_factory
from src.ingestion.load_data import import_csv_dataset
from src.repositories.postgres import PostgresMaintenanceRepository
from src.repositories.postgres_assets import PostgresAssetRepository
from src.security.permissions import Permission, ROLE_PERMISSIONS, Role
from tests.auth_helpers import authorize_app, build_test_user, persist_test_user


@pytest.fixture
def asset_system(clean_postgres_database: str, tmp_path: Path) -> dict[str, Any]:
    import_csv_dataset(database_url=clean_postgres_database)
    session_factory = get_session_factory(clean_postgres_database)
    repository = PostgresMaintenanceRepository(session_factory)
    asset_repository = PostgresAssetRepository(session_factory)
    storage = LocalAttachmentStorage(tmp_path / "attachments")
    asset_management = AssetManagementService(
        asset_repository,
        storage,
        attachment_max_size_bytes=1024,
        frontend_base_url="http://localhost:3000",
    )
    service = ProcessedDataService(
        repository=repository,
        asset_management=asset_management,
    )
    actor = build_test_user(Role.ADMINISTRATOR)
    persist_test_user(session_factory, actor)
    app = create_app()
    app.dependency_overrides[_service] = lambda: service
    authorize_app(app, actor)
    return {
        "client": TestClient(app),
        "app": app,
        "service": service,
        "asset_repository": asset_repository,
        "session_factory": session_factory,
        "storage": storage,
    }


@pytest.mark.postgres
def test_asset_create_update_duplicate_serial_and_stale_conflict(
    asset_system: dict[str, Any],
) -> None:
    client: TestClient = asset_system["client"]
    payload = _asset_payload(client)

    created = client.post("/assets", json=payload)
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["asset_id"] == "TEST_ASSET_001"
    assert profile["lifecycle_status"] == "active"
    assert profile["location_breadcrumb"].endswith("Sân thượng phía Đông")
    assert profile["version"] == 1

    updated = client.patch(
        "/assets/TEST_ASSET_001",
        json={"expected_version": 1, "manufacturer": "Cummins Việt Nam"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["manufacturer"] == "Cummins Việt Nam"
    assert updated.json()["version"] == 2

    stale = client.patch(
        "/assets/TEST_ASSET_001",
        json={"expected_version": 1, "model": "C100"},
    )
    assert stale.status_code == 409

    duplicate_payload = {**payload, "asset_id": "TEST_ASSET_002"}
    duplicate = client.post("/assets", json=duplicate_payload)
    assert duplicate.status_code == 409
    assert "serial" in duplicate.json()["detail"].lower()

    legacy_read = client.get("/assets/TEST_ASSET_001")
    assert legacy_read.status_code == 200
    assert {
        "asset_id",
        "asset_type",
        "location",
        "status",
        "installation_date",
    }.issubset(legacy_read.json())


@pytest.mark.postgres
def test_location_hierarchy_rejects_cycles_and_archive_preserves_assets(
    asset_system: dict[str, Any],
) -> None:
    client: TestClient = asset_system["client"]
    building = client.post(
        "/locations",
        json={"code": "BUILDING-B", "name": "Tòa nhà B", "location_type": "building"},
    )
    assert building.status_code == 201
    building_row = building.json()
    room = client.post(
        "/locations",
        json={
            "code": "ROOM-B101",
            "name": "Phòng B101",
            "location_type": "room",
            "parent_id": building_row["id"],
        },
    )
    assert room.status_code == 201
    room_row = room.json()
    assert room_row["breadcrumb"] == "Tòa nhà B / Phòng B101"

    cycle = client.patch(
        f"/locations/{building_row['id']}",
        json={"expected_version": building_row["version"], "parent_id": room_row["id"]},
    )
    assert cycle.status_code == 409

    parent_archive = client.post(
        f"/locations/{building_row['id']}/archive",
        json={"expected_version": building_row["version"]},
    )
    assert parent_archive.status_code == 409

    seed_locations = client.get("/locations").json()
    assigned = next(
        item
        for item in seed_locations
        if item["asset_count"] > 0 and item["parent_id"] is not None
    )
    before_count = assigned["asset_count"]
    archived = client.post(
        f"/locations/{assigned['id']}/archive",
        json={"expected_version": assigned["version"]},
    )
    assert archived.status_code == 200
    assert archived.json()["asset_count"] == before_count
    assert client.get("/assets/GENERATOR_002/profile").status_code == 200

    create_at_archived = client.post(
        "/assets",
        json=_asset_payload(client, location_id=assigned["id"]),
    )
    assert create_at_archived.status_code == 409

    session_factory = asset_system["session_factory"]
    with session_factory() as session:
        location_actions = set(
            session.scalars(
                select(AuditLog.action).where(AuditLog.action.like("location.%"))
            ).all()
        )
    assert {"location.created", "location.archived"}.issubset(location_actions)


@pytest.mark.postgres
def test_archive_restore_ticket_restriction_qr_and_history(
    asset_system: dict[str, Any],
) -> None:
    client: TestClient = asset_system["client"]
    profile = client.get("/assets/GENERATOR_002/profile").json()
    qr_before = client.get("/assets/GENERATOR_002/qr")
    assert qr_before.status_code == 200
    qr_payload = qr_before.json()
    assert "GENERATOR_002" not in qr_payload["lookup_url"]
    assert "authorization" not in qr_payload["lookup_url"].lower()
    assert client.get("/assets/GENERATOR_002/qr").json() == qr_payload

    archived = client.post(
        "/assets/GENERATOR_002/archive",
        json={
            "expected_version": profile["version"],
            "archive_reason": "Tạm archive để kiểm tra lifecycle test.",
        },
    )
    assert archived.status_code == 200
    archived_profile = archived.json()
    assert archived_profile["lifecycle_status"] == "archived"

    ticket = client.post("/tickets", json=_ticket_payload())
    assert ticket.status_code == 409

    lookup = client.get(f"/asset-lookup/{qr_payload['lookup_token']}")
    assert lookup.status_code == 410

    history = client.get("/assets/GENERATOR_002/history", params={"page_size": 100})
    assert history.status_code == 200
    actions = [item["action"] for item in history.json()["items"]]
    assert actions.count("asset.archived") == 1
    assert any(action.startswith("ticket.") for action in actions)
    assert any(action.startswith("maintenance_log.") for action in actions)

    restored = client.post(
        "/assets/GENERATOR_002/restore",
        json={"expected_version": archived_profile["version"], "lifecycle_status": "active"},
    )
    assert restored.status_code == 200
    assert restored.json()["lifecycle_status"] == "active"
    assert client.get(f"/asset-lookup/{qr_payload['lookup_token']}").status_code == 200
    assert client.post("/tickets", json=_ticket_payload()).status_code == 201

    invalid = client.post(
        "/assets/GENERATOR_002/lifecycle-transition",
        json={
            "expected_version": restored.json()["version"],
            "lifecycle_status": "planned",
        },
    )
    assert invalid.status_code == 409


@pytest.mark.postgres
def test_lifecycle_operational_rules_and_database_constraints(
    asset_system: dict[str, Any],
) -> None:
    client: TestClient = asset_system["client"]
    profile = client.get("/assets/GENERATOR_002/profile").json()

    inactive = client.post(
        "/assets/GENERATOR_002/lifecycle-transition",
        json={"expected_version": profile["version"], "lifecycle_status": "inactive"},
    )
    assert inactive.status_code == 200
    assert inactive.json()["operational_status"] == "out_of_service"
    invalid_running = client.post(
        "/assets/GENERATOR_002/operational-status",
        json={
            "expected_version": inactive.json()["version"],
            "operational_status": "running",
        },
    )
    assert invalid_running.status_code == 409

    active = client.post(
        "/assets/GENERATOR_002/lifecycle-transition",
        json={
            "expected_version": inactive.json()["version"],
            "lifecycle_status": "active",
        },
    )
    assert active.status_code == 200
    retired = client.post(
        "/assets/GENERATOR_002/lifecycle-transition",
        json={
            "expected_version": active.json()["version"],
            "lifecycle_status": "retired",
        },
    )
    assert retired.status_code == 200
    assert retired.json()["operational_status"] == "out_of_service"
    assert client.post("/tickets", json=_ticket_payload()).status_code == 409

    session_factory = asset_system["session_factory"]
    with session_factory() as session, pytest.raises(IntegrityError):
        session.execute(
            text(
                "UPDATE assets SET production_year = 1800 "
                "WHERE asset_id = 'GENERATOR_002'"
            )
        )
        session.commit()


@pytest.mark.postgres
def test_safe_attachment_upload_download_delete_and_audit_redaction(
    asset_system: dict[str, Any],
) -> None:
    client: TestClient = asset_system["client"]
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    uploaded = client.post(
        "/assets/GENERATOR_002/attachments",
        data={"category": "technical_manual"},
        files={"file": ("generator-manual.pdf", pdf, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["checksum"]
    assert "storage_key" not in str(metadata)

    listed = client.get("/assets/GENERATOR_002/attachments")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == metadata["id"]
    downloaded = client.get(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == pdf
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    app = asset_system["app"]
    authorize_app(app, build_test_user(Role.TECHNICIAN))
    assert TestClient(app).get(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    ).status_code == 200
    authorize_app(app, build_test_user(Role.HELPDESK))
    assert TestClient(app).get(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    ).status_code == 403
    authorize_app(app, build_test_user(Role.ADMINISTRATOR))

    dangerous = client.post(
        "/assets/GENERATOR_002/attachments",
        data={"category": "technical_manual"},
        files={"file": ("manual.exe", b"MZ executable", "application/octet-stream")},
    )
    assert dangerous.status_code == 422
    oversized = client.post(
        "/assets/GENERATOR_002/attachments",
        data={"category": "technical_manual"},
        files={"file": ("large.pdf", b"%PDF-" + b"x" * 1024, "application/pdf")},
    )
    assert oversized.status_code == 422
    traversal = client.post(
        "/assets/GENERATOR_002/attachments",
        data={"category": "technical_manual"},
        files={"file": ("..\\secret.pdf", pdf, "application/pdf")},
    )
    assert traversal.status_code == 422

    storage: LocalAttachmentStorage = asset_system["storage"]
    with pytest.raises(AttachmentStorageError, match="Storage key"):
        storage.read("../../secrets.txt")

    attachment = asset_system["asset_repository"].get_attachment(
        "GENERATOR_002", UUID(metadata["id"])
    )
    assert attachment is not None
    storage_key = str(attachment.values["_storage_key"])
    stored_path = storage.root / Path(*storage_key.split("/"))
    stored_path.write_bytes(b"tampered")
    assert client.get(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    ).status_code == 503
    stored_path.write_bytes(pdf)

    deleted = client.delete(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    )
    assert deleted.status_code == 200
    assert client.get(
        f"/assets/GENERATOR_002/attachments/{metadata['id']}"
    ).status_code == 404

    session_factory = asset_system["session_factory"]
    with session_factory() as session:
        audit_rows = session.scalars(
            select(AuditLog).where(AuditLog.action.like("attachment.%"))
        ).all()
    assert {row.action for row in audit_rows} == {
        "attachment.uploaded",
        "attachment.deleted",
    }
    assert all("storage" not in str(row.after_state).lower() for row in audit_rows)


@pytest.mark.postgres
def test_asset_permission_matrix_and_backend_enforcement(
    asset_system: dict[str, Any],
) -> None:
    assert Permission.ASSETS_ARCHIVE in ROLE_PERMISSIONS[Role.PROPERTY_MANAGER]
    assert Permission.ASSETS_CREATE in ROLE_PERMISSIONS[Role.CHIEF_ENGINEER]
    assert Permission.ASSETS_ARCHIVE not in ROLE_PERMISSIONS[Role.CHIEF_ENGINEER]
    assert Permission.ATTACHMENTS_READ in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.ASSETS_UPDATE not in ROLE_PERMISSIONS[Role.HELPDESK]

    app = asset_system["app"]
    helpdesk = build_test_user(Role.HELPDESK)
    authorize_app(app, helpdesk)
    client = TestClient(app)
    profile = client.get("/assets/GENERATOR_002/profile")
    assert profile.status_code == 200
    assert client.patch(
        "/assets/GENERATOR_002",
        json={"expected_version": profile.json()["version"], "model": "Blocked"},
    ).status_code == 403
    assert client.get("/assets/GENERATOR_002/attachments").status_code == 403


def _asset_payload(
    client: TestClient,
    *,
    location_id: str | None = None,
) -> dict[str, Any]:
    if location_id is None:
        locations = client.get("/locations").json()
        location_id = next(
            item["id"]
            for item in locations
            if item["name"] == "Sân thượng phía Đông"
        )
    today = date.today()
    return {
        "asset_id": "TEST_ASSET_001",
        "asset_name": "Máy phát điện kiểm thử 001",
        "asset_type": "generator",
        "asset_category": "power_system",
        "manufacturer": "Cummins",
        "model": "C80",
        "serial_number": "SN-TEST-001",
        "production_year": 2025,
        "location_id": location_id,
        "criticality": "high",
        "lifecycle_status": "active",
        "operational_status": "running",
        "installed_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "commissioned_at": datetime(2025, 1, 2, tzinfo=timezone.utc).isoformat(),
        "ownership_type": "owned",
        "description": "Asset dùng cho integration test.",
        "warranty_start_date": "2025-01-02",
        "warranty_end_date": "2027-01-02",
        "warranty_provider": "Nhà cung cấp kiểm thử",
        "warranty_reference": "WR-001",
        "maintenance_interval_days": 30,
        "last_maintenance_date": (today - timedelta(days=10)).isoformat(),
        "next_maintenance_date": (today + timedelta(days=20)).isoformat(),
    }


def _ticket_payload() -> dict[str, str]:
    return {
        "asset_id": "GENERATOR_002",
        "issue_description": "Kiểm tra asset sau thay đổi lifecycle.",
        "priority": "Cao",
        "failure_category": "Lỗi điện",
        "technician_id": "TECH_001",
        "manager_note": "Lifecycle integration test.",
    }
