from fastapi import Request

from app.settings import Settings
from app.store import SessionStore


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
