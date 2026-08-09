"""Safe attachment validation and local-development object storage."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePath
import re
import tempfile
from typing import Protocol
from uuid import uuid4


class AttachmentValidationError(ValueError):
    """Raised when an uploaded body or filename violates the attachment contract."""


class AttachmentStorageError(RuntimeError):
    """Raised when attachment bytes cannot be stored or retrieved safely."""


@dataclass(frozen=True)
class ValidatedAttachment:
    """Validated attachment metadata and immutable bytes."""

    original_filename: str
    extension: str
    media_type: str
    size_bytes: int
    checksum: str
    content: bytes


class AttachmentStorage(Protocol):
    """Minimal object-storage boundary used by the asset service."""

    def save(
        self,
        attachment: ValidatedAttachment,
        *,
        namespace: str = "assets",
    ) -> str: ...

    def read(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...

    def check_integrity(
        self, storage_key: str, *, expected_checksum: str
    ) -> str: ...


_KEY_PATTERN = re.compile(
    r"^(?:assets|work-orders|inventory)/[0-9a-f]{2}/"
    r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg)$"
)
_ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def validate_attachment(
    *,
    filename: str,
    claimed_media_type: str | None,
    content: bytes,
    max_size_bytes: int,
) -> ValidatedAttachment:
    """Validate filename, signature, media type, size, and checksum."""

    normalized_name = filename.strip()
    if (
        not normalized_name
        or len(normalized_name) > 255
        or "\x00" in normalized_name
        or "/" in normalized_name
        or "\\" in normalized_name
        or PurePath(normalized_name).name != normalized_name
    ):
        raise AttachmentValidationError("Tên tệp không hợp lệ hoặc chứa đường dẫn.")
    extension = Path(normalized_name).suffix.casefold()
    expected_media_type = _ALLOWED_EXTENSIONS.get(extension)
    if expected_media_type is None:
        raise AttachmentValidationError(
            "Chỉ chấp nhận tệp PDF, PNG, JPG hoặc JPEG."
        )
    if not content:
        raise AttachmentValidationError("Tệp tải lên không được để trống.")
    if len(content) > max_size_bytes:
        raise AttachmentValidationError(
            f"Tệp vượt quá giới hạn {max_size_bytes // (1024 * 1024)} MB."
        )
    detected_media_type = _detect_media_type(content)
    normalized_claim = (claimed_media_type or "").split(";", maxsplit=1)[0].strip().casefold()
    if detected_media_type != expected_media_type or normalized_claim != expected_media_type:
        raise AttachmentValidationError(
            "Định dạng nội dung, phần mở rộng và MIME type của tệp không khớp."
        )
    return ValidatedAttachment(
        original_filename=normalized_name,
        extension=extension,
        media_type=expected_media_type,
        size_bytes=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        content=content,
    )


class LocalAttachmentStorage:
    """Atomic local storage for a single-node pilot environment."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def save(
        self,
        attachment: ValidatedAttachment,
        *,
        namespace: str = "assets",
    ) -> str:
        if namespace not in {"assets", "work-orders", "inventory"}:
            raise AttachmentStorageError("Attachment storage namespace không hợp lệ.")
        identifier = uuid4().hex
        key = f"{namespace}/{identifier[:2]}/{identifier}{attachment.extension}"
        target = self._resolve_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{identifier}.",
            suffix=".tmp",
            dir=target.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(attachment.content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
        except OSError as exc:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise AttachmentStorageError("Không thể lưu tệp đính kèm vào local storage.") from exc
        return key

    def read(self, storage_key: str) -> bytes:
        target = self._resolve_key(storage_key)
        try:
            return target.read_bytes()
        except FileNotFoundError as exc:
            raise AttachmentStorageError("Nội dung tệp đính kèm không còn khả dụng.") from exc
        except OSError as exc:
            raise AttachmentStorageError("Không thể đọc tệp đính kèm.") from exc

    def delete(self, storage_key: str) -> None:
        target = self._resolve_key(storage_key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise AttachmentStorageError("Không thể xóa nội dung tệp đính kèm.") from exc

    def check_integrity(
        self, storage_key: str, *, expected_checksum: str
    ) -> str:
        """Stream a checksum without exposing the resolved local path."""

        try:
            target = self._resolve_key(storage_key)
        except AttachmentStorageError:
            return "invalid_key"
        try:
            digest = hashlib.sha256()
            with target.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
        except FileNotFoundError:
            return "missing"
        except OSError:
            return "unreadable"
        actual = digest.hexdigest()
        return "ok" if actual == expected_checksum else "checksum_mismatch"

    def count_orphan_files(self, referenced_keys: set[str]) -> int:
        """Count every storage-root file not referenced by active metadata."""

        count = 0
        if not self.root.exists():
            return 0
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            key = path.relative_to(self.root).as_posix()
            if key not in referenced_keys:
                count += 1
        return count

    def _resolve_key(self, storage_key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(storage_key):
            raise AttachmentStorageError("Storage key của tệp đính kèm không hợp lệ.")
        target = (self.root / Path(*storage_key.split("/"))).resolve()
        if not target.is_relative_to(self.root):
            raise AttachmentStorageError("Storage key nằm ngoài attachment storage root.")
        return target


def _detect_media_type(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None
