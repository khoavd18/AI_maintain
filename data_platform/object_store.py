"""Run-scoped local objects with an optional, disabled-by-default S3 copy."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil

from data_platform.config import DataPlatformSettings


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    path: Path
    sha256: str
    size_bytes: int


def checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class LocalObjectStore:
    """Filesystem implementation using partitioned, immutable object keys."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, source: Path, key: str) -> StoredObject:
        destination = (self._root / "objects" / key).resolve()
        root = (self._root / "objects").resolve()
        if root not in destination.parents:
            raise ValueError("Object key escapes the configured local object root.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = checksum(source)
        if destination.exists():
            if checksum(destination) != source_hash:
                raise FileExistsError(f"Immutable object key already has different bytes: {key}")
        else:
            temporary = destination.with_suffix(destination.suffix + ".partial")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        return StoredObject(key, destination, source_hash, destination.stat().st_size)


class S3ObjectStore:
    """Optional S3 copy; imports the SDK only when explicitly enabled."""

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket

    def put(self, source: Path, key: str) -> StoredObject:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional runtime
            raise RuntimeError("Install the data-platform-s3 extra before enabling S3.") from exc
        digest = checksum(source)
        client = boto3.client("s3")
        client.upload_file(
            str(source),
            self._bucket,
            key,
            ExtraArgs={
                "ContentType": "text/csv",
                "ServerSideEncryption": "AES256",
                "Metadata": {"sha256": digest},
            },
        )
        return StoredObject(key, source, digest, source.stat().st_size)


def build_object_store(settings: DataPlatformSettings):
    if settings.object_store == "s3":
        assert settings.s3_bucket is not None
        return S3ObjectStore(settings.s3_bucket)
    return LocalObjectStore(settings.data_root)
