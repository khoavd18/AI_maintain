"""FastAPI entrypoint for the AI Maintenance Copilot."""

from fastapi import FastAPI

from src.api.routes import router
from src.config.settings import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="AI decision-support layer for predictive maintenance workflows.",
        version="0.1.0",
    )

    app.include_router(router)

    return app


app = create_app()
