"""FastAPI application entry point.

Local API:   python -m uvicorn app.main:app --reload --port 8000   (from backend/)
Production:  python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT

When the built frontend (frontend/dist) exists, the same app also serves it,
so the deployed site is single-origin and needs no CORS. During local
development the Vite dev server serves the frontend instead.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app import __version__
from app.api import analysis, datasets, health, instruments, observations, package, research, validation
from app.frontend import mount_frontend
from app.persistence import ImportArchive
from app.settings import Settings
from app.store import SessionStore

# backend/app/main.py -> repository root -> frontend/dist, independent of the working directory.
DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

logger = logging.getLogger("goldlensai")


def create_app(
    frontend_dist: Path | None = DEFAULT_FRONTEND_DIST, settings: Settings | None = None
) -> FastAPI:
    app = FastAPI(
        title="GoldLensAI API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    # Research responses are large JSON documents; compress them over the wire.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Imported gold rows are saved under settings.store_dir and reloaded here (see app/store.py).
    app.state.settings = settings or Settings.from_env()
    store_dir = app.state.settings.store_dir
    archive = ImportArchive(store_dir) if store_dir else None
    if archive and app.state.settings.seed_dir:
        archive.seed_if_empty(app.state.settings.seed_dir)
    app.state.store = SessionStore.open(archive)
    # Real data loaded from disk gets its research straight away, so no page waits for a run.
    try:
        research.run_with_assumptions(app.state.store)
    except Exception:  # never block startup on research; the Research page can still run it
        logger.exception("Startup research run failed")

    # Every route lives under /api so the Vite dev proxy can forward it unchanged.
    for module in (health, instruments, datasets, observations, research, package, analysis, validation):
        app.include_router(module.router, prefix="/api")

    # Registered last so API routes always take precedence.
    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        mount_frontend(app, frontend_dist)
    elif frontend_dist is not None:
        logger.info("No built frontend at %s; serving the API only.", frontend_dist)
    return app


app = create_app()
