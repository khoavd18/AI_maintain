"""Stable HTTP error translation shared by inventory route groups."""

from fastapi import HTTPException, status

from src.asset_management.storage import AttachmentStorageError, AttachmentValidationError
from src.inventory_management.service import (
    InventoryAuthorizationError,
    InventoryConflictError,
    InventoryDomainError,
    InventoryNotFoundError,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    UnsupportedStorageOperationError,
)


def _handle(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except InventoryAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (InventoryNotFoundError, RecordNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        InventoryConflictError,
        DuplicateIdentifierError,
        IntegrityViolationError,
        StaleRecordError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (AttachmentValidationError, InventoryDomainError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (
        AttachmentStorageError,
        StorageUnavailableError,
        UnsupportedStorageOperationError,
        RepositoryError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
