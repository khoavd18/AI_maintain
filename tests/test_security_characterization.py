"""Direct characterization of security primitives and pure projections."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest

from src.database.models import User
from src.security.audit import safe_metadata
from src.security.errors import AuthenticationError as CanonicalAuthenticationError
from src.security.passwords import hash_password, verify_password
from src.security.permissions import Permission, Role, permissions_for_role
from src.security.principal import CurrentUser as PrincipalCurrentUser
from src.security.service import (
    AuthenticationError,
    CurrentUser,
    normalize_identifier,
    normalize_optional,
    normalize_optional_identifier,
    user_response_values,
)
from src.security.tokens import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    InvalidAccessTokenError,
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
    refresh_session_id,
    token_hash_matches,
)


SIGNING_SECRET = "test-only-signing-secret-with-more-than-32-characters"
PREVIOUS_SIGNING_SECRET = "previous-test-signing-secret-with-more-than-32-characters"
PASSWORD = "Internal-Test-Password-42!"
NOW = datetime.now(timezone.utc) - timedelta(minutes=1)


def _principal(*, session_id: UUID | None = None) -> CurrentUser:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CurrentUser(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        username="operator.test",
        email="operator@example.invalid",
        display_name="Operator Test",
        role=Role.PROPERTY_MANAGER,
        permissions=permissions_for_role(Role.PROPERTY_MANAGER),
        technician_id=None,
        is_active=True,
        version=4,
        session_id=session_id or UUID("22222222-2222-4222-8222-222222222222"),
        created_at=created_at,
        updated_at=created_at,
        last_login_at=created_at,
    )


def test_current_user_is_frozen_value_object_and_both_imports_are_identical() -> None:
    assert CurrentUser is PrincipalCurrentUser
    assert AuthenticationError is CanonicalAuthenticationError
    first = _principal()
    second = _principal()

    assert first == second
    assert first.has(Permission.AUDIT_LOGS_READ)
    with pytest.raises(FrozenInstanceError):
        first.username = "changed"  # type: ignore[misc]


def test_identifier_and_optional_normalization_preserve_current_rules() -> None:
    assert normalize_identifier("  OPERATOR.TEST ") == "operator.test"
    assert normalize_identifier("  USER@EXAMPLE.COM ") == "user@example.com"
    assert normalize_optional_identifier(None) is None
    assert normalize_optional_identifier("") is None
    assert normalize_optional_identifier("  USER@EXAMPLE.COM ") == "user@example.com"
    assert normalize_optional("  technician-42 ") == "technician-42"
    assert normalize_optional(0) == "0"
    assert normalize_optional(None) is None
    with pytest.raises(AuthenticationError):
        normalize_identifier("   ")


def test_user_response_projection_has_canonical_role_permissions_and_no_password() -> None:
    user_id = uuid4()
    user = User(
        id=user_id,
        username="operator.test",
        email="operator@example.invalid",
        password_hash="$argon2id$secret-that-must-not-be-returned",
        display_name="Operator Test",
        role=Role.TECHNICIAN.value,
        technician_id="TECH_042",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
        last_login_at=NOW,
        version=2,
    )

    response = user_response_values(user)

    assert response["id"] == user_id
    assert response["role"] == Role.TECHNICIAN
    assert response["role_display_name"]
    assert response["permissions"] == sorted(
        permission.value for permission in permissions_for_role(Role.TECHNICIAN)
    )
    assert response["technician_id"] == "TECH_042"
    assert "password" not in response
    assert "password_hash" not in response


def test_current_user_response_projection_matches_persisted_user_contract() -> None:
    response = user_response_values(_principal())

    assert response["id"] == _principal().id
    assert response["role"] == Role.PROPERTY_MANAGER
    assert response["permissions"] == sorted(
        permission.value for permission in permissions_for_role(Role.PROPERTY_MANAGER)
    )
    assert "session_id" not in response


def test_access_token_contains_required_claims_and_decodes_current_values() -> None:
    user_id = uuid4()
    session_id = uuid4()
    token, expires_at = create_access_token(
        user_id=user_id,
        session_id=session_id,
        role=Role.ADMINISTRATOR.value,
        user_version=7,
        signing_secret=SIGNING_SECRET,
        lifetime_minutes=15,
        now=NOW,
    )

    payload = jwt.decode(
        token,
        SIGNING_SECRET,
        algorithms=[ALGORITHM],
        audience=AUDIENCE,
        issuer=ISSUER,
    )
    assert set(("sub", "sid", "role", "ver", "jti", "type", "iat", "exp")) <= payload.keys()
    assert payload["sub"] == str(user_id)
    assert payload["sid"] == str(session_id)
    assert payload["role"] == Role.ADMINISTRATOR.value
    assert payload["ver"] == 7
    assert payload["type"] == "access"

    claims = decode_access_token(token, SIGNING_SECRET)
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.role == Role.ADMINISTRATOR.value
    assert claims.user_version == 7
    assert int(claims.expires_at.timestamp()) == int(expires_at.timestamp())


def test_access_token_accepts_one_previous_signing_key_but_rejects_invalid_tokens() -> None:
    token, _ = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        role=Role.PROPERTY_MANAGER.value,
        user_version=1,
        signing_secret=PREVIOUS_SIGNING_SECRET,
        lifetime_minutes=15,
        now=NOW,
    )
    assert decode_access_token(token, SIGNING_SECRET, PREVIOUS_SIGNING_SECRET).role == (
        Role.PROPERTY_MANAGER.value
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, SIGNING_SECRET)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token + "tampered", SIGNING_SECRET, PREVIOUS_SIGNING_SECRET)


@pytest.mark.parametrize(
    "payload_change",
    [
        {"type": "refresh"},
        {"role": None},
    ],
)
def test_access_token_rejects_wrong_type_and_invalid_claim_values(payload_change: dict[str, object]) -> None:
    user_id = uuid4()
    session_id = uuid4()
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "role": Role.ADMINISTRATOR.value,
        "ver": 1,
        "jti": "token-id",
        "type": "access",
        "iat": NOW,
        "exp": NOW + timedelta(minutes=15),
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    payload.update(payload_change)
    token = jwt.encode(payload, SIGNING_SECRET, algorithm=ALGORITHM)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, SIGNING_SECRET)


def test_access_token_rejects_expired_and_missing_required_claims() -> None:
    expired, _ = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        role=Role.ADMINISTRATOR.value,
        user_version=1,
        signing_secret=SIGNING_SECRET,
        lifetime_minutes=1,
        now=NOW - timedelta(minutes=5),
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(expired, SIGNING_SECRET)

    missing_claim = jwt.encode(
        {
            "sub": str(uuid4()),
            "sid": str(uuid4()),
            "role": Role.ADMINISTRATOR.value,
            "ver": 1,
            "jti": "token-id",
            "type": "access",
            "iat": NOW,
            "exp": NOW + timedelta(minutes=15),
            "iss": ISSUER,
        },
        SIGNING_SECRET,
        algorithm=ALGORITHM,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(missing_claim, SIGNING_SECRET)


def test_refresh_and_csrf_values_are_opaque_and_hash_comparison_is_exact() -> None:
    session_id = uuid4()
    refresh_token = create_refresh_token(session_id)
    csrf_token = create_csrf_token()

    assert refresh_session_id(refresh_token) == session_id
    assert len(csrf_token) >= 32
    assert hash_token(refresh_token) != refresh_token
    assert token_hash_matches(refresh_token, hash_token(refresh_token))
    assert not token_hash_matches(refresh_token + "x", hash_token(refresh_token))
    assert token_hash_matches(csrf_token, hash_token(csrf_token))

    for malformed in ("", "not-a-token", f"{session_id}.short", f"not-a-uuid.{refresh_token}"):
        with pytest.raises(ValueError):
            refresh_session_id(malformed)


def test_password_hashing_accepts_argon2_hashes_and_never_returns_plaintext() -> None:
    password_hash = hash_password(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash
    assert verify_password(PASSWORD, password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password(PASSWORD, "malformed-hash")


def test_safe_metadata_filters_secret_keys_and_non_scalar_values() -> None:
    metadata = safe_metadata(
        {
            "password": PASSWORD,
            "password_hash": "hash",
            "access_token": "token-value",
            "Authorization": "Bearer secret",
            "cookie_value": "cookie-secret",
            "safe": "kept",
            "count": 2,
            "nested": {"secret": "not-allowed"},
            "long": "x" * 400,
        }
    )

    assert metadata is not None
    assert metadata["safe"] == "kept"
    assert metadata["count"] == 2
    assert metadata["long"] == "x" * 300
    assert "password" not in str(metadata).lower()
    assert "token" not in str(metadata).lower()
    assert "authorization" not in str(metadata).lower()
    assert "cookie" not in str(metadata).lower()
    assert "nested" not in metadata
