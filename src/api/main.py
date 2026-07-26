"""FastAPI entrypoint for the AI Maintenance Copilot."""

from contextlib import asynccontextmanager
import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.routes import router
from src.api.services import get_processed_data_service
from src.config.settings import get_settings
from src.inventory_management.routes import router as inventory_router
from src.maintenance_management.routes import router as maintenance_planning_router
from src.operations.logging import configure_structured_logging, log_event
from src.operations.routes import router as operations_router
from src.operations.service import build_operations_service
from src.repositories.contracts import RepositoryError
from src.security.routes import router as security_router
from src.ticket_management.routes import router as ticket_operations_router

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
logger = logging.getLogger("maintenance.api")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Validate configured primary storage without creating or migrating tables."""

    try:
        get_processed_data_service().repository.check_health()
        if get_settings().storage_backend == "postgresql":
            build_operations_service().repository.check_health()
    except (RepositoryError, OSError, ValueError) as exc:
        raise RuntimeError(
            "Configured primary storage is unavailable or not migrated. "
            "Start PostgreSQL and run `alembic upgrade head`; no CSV fallback was used."
        ) from exc
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    configure_structured_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        description="AI decision-support layer for predictive maintenance workflows.",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.storage_backend = settings.storage_backend

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.get_trusted_hosts(),
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        started = time.monotonic()
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid4())
        )
        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "api.request_failed",
                "API request failed.",
                request_id=request.state.request_id,
                http_method=request.method,
                http_path=request.url.path,
                http_status=500,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        response.headers["X-Request-ID"] = request.state.request_id
        log_event(
            logger,
            logging.INFO,
            "api.request_completed",
            "API request completed.",
            request_id=request.state.request_id,
            http_method=request.method,
            http_path=request.url.path,
            http_status=response.status_code,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return response

    app.include_router(security_router)
    app.include_router(router)
    app.include_router(ticket_operations_router)
    app.include_router(maintenance_planning_router)
    app.include_router(inventory_router)
    app.include_router(operations_router)

    return app


app = create_app()
