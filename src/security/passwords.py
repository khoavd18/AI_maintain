"""Argon2id password hashing helpers."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_HASHER = PasswordHasher()
_DUMMY_HASH = _HASHER.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    """Hash a validated password with Argon2id."""

    if len(password) < 12 or len(password) > 256:
        raise ValueError("Mật khẩu phải có từ 12 đến 256 ký tự.")
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify without leaking malformed-hash or mismatch details."""

    try:
        return _HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def consume_dummy_verification(password: str) -> None:
    """Reduce identifier timing differences for unknown login names."""

    verify_password(password, _DUMMY_HASH)
