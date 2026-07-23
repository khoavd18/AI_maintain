"""Short-lived JWT access tokens and opaque refresh token helpers."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from uuid import UUID

import jwt

ISSUER = "ai-maintenance-copilot"
AUDIENCE = "ai-maintenance-copilot-api"
ALGORITHM = "HS256"


class InvalidAccessTokenError(ValueError):
    """Raised for any invalid, expired, or malformed access token."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    role: str
    user_version: int
    token_id: str
    expires_at: datetime


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    role: str,
    user_version: int,
    signing_secret: str,
    lifetime_minutes: int,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=lifetime_minutes)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "role": role,
        "ver": user_version,
        "jti": secrets.token_hex(16),
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    return jwt.encode(payload, signing_secret, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str, signing_secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            signing_secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={
                "require": ["sub", "sid", "role", "ver", "jti", "type", "iat", "exp"]
            },
        )
        if payload["type"] != "access":
            raise InvalidAccessTokenError("Unexpected token type")
        return AccessClaims(
            user_id=UUID(str(payload["sub"])),
            session_id=UUID(str(payload["sid"])),
            role=str(payload["role"]),
            user_version=int(payload["ver"]),
            token_id=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(float(payload["exp"]), timezone.utc),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("Invalid access token") from exc


def create_refresh_token(session_id: UUID) -> str:
    return f"{session_id}.{secrets.token_urlsafe(48)}"


def refresh_session_id(token: str) -> UUID:
    try:
        identifier, secret = token.split(".", maxsplit=1)
        if len(secret) < 32:
            raise ValueError
        return UUID(identifier)
    except (AttributeError, ValueError) as exc:
        raise ValueError("Invalid refresh token") from exc


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_hash_matches(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(value), expected_hash)
