"""Liveness endpoint.

Reports only that the API process is running. It deliberately says nothing
about datasets or research results; those get their own endpoints.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__

API_VERSION = "1"

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="Always 'ok' when the process can serve requests.")
    service: str = Field(description="Service identifier.")
    version: str = Field(description="Backend application version.")
    api_version: str = Field(description="Version of the public API contract.")
    server_time: datetime = Field(description="Current server time, UTC.")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="goldlensai-backend",
        version=__version__,
        api_version=API_VERSION,
        server_time=datetime.now(UTC),
    )
