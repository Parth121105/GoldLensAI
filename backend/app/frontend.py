"""Serve the built React frontend (frontend/dist) from FastAPI.

Rules:
  * /api and /api/* never reach the frontend route, so unknown API paths are
    404 for every method and API routes keep their own 405 responses.
  * Existing files in dist are served as-is (hashed bundles under /assets).
  * A missing file with an extension (e.g. /assets/old.js) is a 404, not
    index.html, so broken asset links fail visibly.
  * Any other GET path falls back to index.html for client-side routing.
  * Paths that resolve outside dist are refused.
"""

from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match
from starlette.types import Scope

# index.html must be revalidated so new deployments are picked up; hashed
# assets can be cached by the browser.
INDEX_HEADERS = {"Cache-Control": "no-cache"}


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class _NonApiRoute(APIRoute):
    """A route that never matches /api paths.

    Matching and then refusing would turn a POST to an unknown API path into a
    405 (the path "exists" for GET) and a HEAD on a GET-only API route into a 404.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if is_api_path(scope.get("path", "")):
            return Match.NONE, {}
        return super().matches(scope)


def mount_frontend(app: FastAPI, dist: Path) -> None:
    dist = dist.resolve()
    index = dist / "index.html"

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    def frontend(full_path: str) -> FileResponse:
        if full_path:
            candidate = (dist / full_path).resolve()
            if not candidate.is_relative_to(dist):
                raise HTTPException(status_code=404, detail="Not Found")
            if candidate.is_file():
                # /index.html requested directly must also be revalidated after a deploy.
                return FileResponse(candidate, headers=INDEX_HEADERS if candidate == index else None)
            if PurePosixPath(full_path).suffix:
                raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(index, headers=INDEX_HEADERS)

    app.router.add_api_route(
        "/{full_path:path}",
        frontend,
        methods=["GET", "HEAD"],
        include_in_schema=False,
        route_class_override=_NonApiRoute,
    )
