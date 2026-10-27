from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app

# API-only app: these tests must not depend on whether frontend/dist has been built.
# Frontend serving is covered in test_frontend_serving.py.
client = TestClient(create_app(frontend_dist=None))


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "goldlensai-backend"
    assert body["version"] == __version__
    assert body["api_version"] == "1"


def test_health_has_exactly_the_documented_fields():
    body = client.get("/api/health").json()

    assert set(body) == {"status", "service", "version", "api_version", "server_time"}


def test_health_server_time_is_current_utc():
    body = client.get("/api/health").json()

    server_time = datetime.fromisoformat(body["server_time"])
    assert server_time.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - server_time) < timedelta(seconds=30)


def test_health_rejects_other_methods():
    assert client.post("/api/health").status_code == 405


def test_routes_outside_api_prefix_are_not_served():
    assert client.get("/health").status_code == 404


def test_openapi_schema_documents_health():
    schema = client.get("/api/openapi.json").json()

    assert "/api/health" in schema["paths"]
