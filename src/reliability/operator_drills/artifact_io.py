"""Path-safe durability primitives shared by reliability artifact drills."""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import hashlib
import os
from pathlib import Path
import re


_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _prepare_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Configured allowed root must be a directory.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _contained_child(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Generated artifact is outside the configured allowed root.")
    return target


def _validate_safe_filename(value: str) -> None:
    if not _SAFE_FILENAME_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Artifact name must be a safe generated filename.")


def _validate_sha256(value: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("SHA-256 value must contain 64 lowercase hexadecimal characters.")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _sync_file(path: Path) -> None:
    # Windows requires a writable descriptor for FlushFileBuffers/os.fsync.
    with path.open("rb+") as source:
        _sync_descriptor(source.fileno())


def _sync_descriptor(descriptor: int) -> None:
    unsupported = {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in unsupported:
            raise


def _sync_directory(path: Path) -> None:
    """Persist directory entries where the host filesystem supports it."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        unsupported_open = {
            errno.EACCES,
            errno.EINVAL,
            errno.EPERM,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if os.name == "nt" or exc.errno in unsupported_open:
            return
        raise
    try:
        _sync_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _unlink_regular_file(path: Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return _aware_utc(value).isoformat().replace("+00:00", "Z")
