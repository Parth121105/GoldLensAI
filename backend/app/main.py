"""FastAPI application entry point.

Run from backend/:  python -m uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI

from app import __version__
from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="GoldLensAI API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    # Every route lives under /api so the Vite dev proxy can forward it unchanged.
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
