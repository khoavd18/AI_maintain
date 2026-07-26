"""Safe default tests for PM8 reliability tooling and secret rotation."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.asset_management.storage import (
    LocalAttachmentStorage,
    ValidatedAttachment,
)
from src.config.settings import Settings
from src.reliability.backup_restore import build_pg_commands, sha256_file
from src.reliability.load_harness import (
    Sample,
    _load_mutations,
    _summarize,
    _validated_base_url,
)
from src.reliability.profiles import PROFILES
from src.operations.jobs import _atomic_publish_directory
from src.operations.service import (
    OperationsAuthorizationError,
    OperationsService,
)
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser
from src.security.tokens import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
)


def test_default_profiles_are_bounded_and_labelled_assumptions() -> None:
    assert PROFILES["baseline"].concurrent_users == 4
    assert PROFILES["stress"].duration_seconds <= 60
    assert PROFILES["recovery"].duration_seconds <= 60
    assert PROFILES["soak"].extended is True
    assert PROFILES["soak"].duration_seconds <= 900


def test_load_summary_reports_percentiles_failures_and_outbox() -> None:
    report = _summarize(
        profile=PROFILES["baseline"],
        samples=[
            Sample("/health/live", 200, 1.0, "success"),
            Sample("/notifications", 401, 2.0, "expected_authorization_failure"),
            Sample("/assets", 503, 3.0, "database_connection_failure"),
            Sample("/tickets", None, 4.0, "timeout"),
        ],
        elapsed_seconds=1.0,
        before_metrics={"pending_outbox_count": 2},
        after_metrics={"pending_outbox_count": 0},
        base_url="http://testserver",
    )
    assert report["total_requests"] == 4
    assert report["latency_ms"] == {
        "p50": 2.0,
        "p95": 4.0,
        "p99": 4.0,
        "max": 4.0,
    }
    assert report["expected_authorization_failures"] == 1
    assert report["database_connection_failures"] == 1
    assert report["timeouts"] == 1
    assert report["outbox_before"]["pending_outbox_count"] == 2
    assert report["production_readiness_claim"] is False


def test_load_harness_rejects_credentials_and_external_targets(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="credential-free"):
        _validated_base_url("http://operator:secret@example.test")

    fixture = tmp_path / "mutations.json"
    fixture.write_text(
        '[{"method":"GET","path":"https://external.example.test/capture"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="local absolute paths"):
        _load_mutations(fixture)


def test_backup_commands_are_separate_and_do_not_embed_password(tmp_path: Path) -> None:
    archive = tmp_path / "backup.dump"
    commands = build_pg_commands(
        "postgresql+psycopg://pilot_user:super-secret@db:5432/pilot",
        "pilot_restore",
        archive,
    )
    flattened = " ".join(
        (*commands.dump, *commands.create_restore_database, *commands.restore)
    )
    assert "super-secret" not in flattened
    assert "pilot_restore" in commands.create_restore_database
    assert "pilot_restore" in commands.restore
    assert "pilot" in commands.dump


def test_backup_checksum_detects_change(tmp_path: Path) -> None:
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"first")
    first = sha256_file(archive)
    archive.write_bytes(b"second")
    assert sha256_file(archive) != first


def test_signing_key_rotation_accepts_one_previous_key_only() -> None:
    now = datetime.now(timezone.utc)
    old_key = "o" * 48
    new_key = "n" * 48
    token, _ = create_access_token(
        user_id=__import__("uuid").uuid4(),
        session_id=__import__("uuid").uuid4(),
        role="administrator",
        user_version=1,
        signing_secret=old_key,
        lifetime_minutes=15,
        now=now,
    )
    claims = decode_access_token(token, new_key, old_key)
    assert claims.role == "administrator"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, new_key)


def test_pilot_rejects_default_database_secret_and_invalid_rotation_key() -> None:
    with pytest.raises(ValidationError, match="development database credentials"):
        Settings(
            app_environment="pilot",
            auth_cookie_secure=True,
            token_signing_secret="s" * 48,
        )
    with pytest.raises(ValidationError, match="PREVIOUS"):
        Settings(token_signing_previous_secret="short")
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            app_environment="pilot",
            auth_cookie_secure=True,
            token_signing_secret="s" * 48,
            database_url=(
                "postgresql+psycopg://replace_with_database_user:"
                "replace_with_random_database_password@db:5432/"
                "replace_with_database_name"
            ),
        )
    with pytest.raises(ValidationError, match="must differ"):
        Settings(
            token_signing_secret="s" * 48,
            token_signing_previous_secret="s" * 48,
        )


def test_attachment_integrity_is_path_safe_and_reports_missing(
    tmp_path: Path,
) -> None:
    storage = LocalAttachmentStorage(tmp_path)
    attachment = ValidatedAttachment(
        original_filename="manual.pdf",
        extension=".pdf",
        media_type="application/pdf",
        size_bytes=8,
        checksum=__import__("hashlib").sha256(b"%PDF-ok").hexdigest(),
        content=b"%PDF-ok",
    )
    key = storage.save(attachment)
    assert storage.check_integrity(key, expected_checksum=attachment.checksum) == "ok"
    storage.delete(key)
    assert (
        storage.check_integrity(key, expected_checksum=attachment.checksum)
        == "missing"
    )
    assert (
        storage.check_integrity("../secret.pdf", expected_checksum="0" * 64)
        == "invalid_key"
    )
    (tmp_path / ".unexpected").write_bytes(b"stale-temp")
    rogue = tmp_path / "unexpected" / "rogue.bin"
    rogue.parent.mkdir()
    rogue.write_bytes(b"rogue")
    assert storage.count_orphan_files(set()) == 2


def test_dead_letter_redrive_requires_operator_permission() -> None:
    now = datetime.now(timezone.utc)
    actor = CurrentUser(
        id=uuid4(),
        username="pm8-technician",
        email="pm8-technician@example.test",
        display_name="PM8 Technician",
        role=Role.TECHNICIAN,
        permissions=permissions_for_role(Role.TECHNICIAN),
        technician_id="PM8-TECH",
        is_active=True,
        version=1,
        session_id=uuid4(),
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    service = OperationsService(  # type: ignore[arg-type]
        object(),
        worker_stale_seconds=60,
    )
    with pytest.raises(OperationsAuthorizationError):
        service.redrive_outbox_event(
            uuid4(),
            idempotency_key="pm8-unauthorized-redrive",
            actor=actor,
            audit_context=AuditContext(
                actor_user_id=actor.id,
                actor_display_name=actor.display_name,
                request_id="pm8-unauthorized-redrive",
            ),
        )


def test_analytics_publication_failure_restores_last_valid_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "processed"
    staging = tmp_path / "staging"
    target.mkdir()
    staging.mkdir()
    (target / "risk_scores.csv").write_text("last-valid", encoding="utf-8")
    (staging / "risk_scores.csv").write_text("new", encoding="utf-8")
    real_replace = __import__("os").replace
    calls = 0

    def fail_publish(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("controlled publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr("src.operations.jobs.os.replace", fail_publish)
    with pytest.raises(OSError, match="controlled"):
        _atomic_publish_directory(staging, target)
    assert (target / "risk_scores.csv").read_text(encoding="utf-8") == "last-valid"
