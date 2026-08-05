"""HTTP error mapping shared by focused API routers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from src.analytics.errors import AssetNotFoundError, ProcessedDataNotFoundError
from src.repositories.contracts import RepositoryError, StorageUnavailableError


def handle_service_errors(function: Callable[..., Any], **kwargs: Any) -> Any:
    """Map read-service failures to the established legacy status codes."""

    try:
        return function(**kwargs)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
