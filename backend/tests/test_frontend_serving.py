"""Single-origin deployment: FastAPI serves the API and the built frontend.

Uses a small stand-in dist directory so the tests don't depend on a real build.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import DEFAULT_FRONTEND_DIST, create_app

INDEX_HTML = "<!doctype html><title>GoldLensAI test index</title><div id=root></div>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "index-abc123.js").write_text("console.log('app')", encoding="utf-8")
    (root / "assets" / "index-abc123.css").write_text("body{}", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside dist", encoding="utf-8")
    return root


@pytest.fixture
def client(dist: Path) -> TestClient:
    return TestClient(create_app(frontend_dist=dist))


# --- Frontend -------------------------------------------------------------------


def test_root_serves_index_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "GoldLensAI test index" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_head_request_on_root(client):
    assert client.head("/").status_code == 200


@pytest.mark.parametrize(
    ("path", "content_type", "body"),
    [
        ("/assets/index-abc123.js", "javascript", "console.log('app')"),
        ("/assets/index-abc123.css", "text/css", "body{}"),
        ("/favicon.svg", "image/svg+xml", "<svg"),
    ],
)
def test_static_files_are_served(client, path, content_type, body):
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert body in response.text


@pytest.mark.parametrize("path", ["/research", "/validation/GOLDTEN", "/dossier/x/y"])
def test_client_routes_fall_back_to_index(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert "GoldLensAI test index" in response.text


@pytest.mark.parametrize("path", ["/assets/missing.js", "/missing.png", "/old/bundle.css"])
def test_missing_files_are_404_not_index(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert "GoldLensAI test index" not in response.text


@pytest.mark.parametrize("path", ["/..%2fsecret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"])
def test_paths_outside_dist_are_refused(client, path):
    response = client.get(path)

    assert "outside dist" not in response.text


# --- API routing is unchanged --------------------------------------------------------


def test_health_is_json_not_index(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/unknown", "/api/v1/research/x", "/api/health/extra"])
def test_unknown_api_paths_are_404_json_never_index(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "GoldLensAI test index" not in response.text


@pytest.mark.parametrize("path", ["/api/instruments", "/api/datasets", "/api/observations"])
def test_dashboard_api_routes_return_json_with_frontend_mounted(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_research_before_any_run_is_json_null_not_index(client):
    response = client.get("/api/research")  # nothing run yet

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() is None


def test_dashboard_client_routes_fall_back_to_index(client):
    for path in ("/contracts", "/data", "/research", "/methodology"):
        assert "GoldLensAI test index" in client.get(path).text


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
@pytest.mark.parametrize("path", ["/api/unknown", "/api/v1/research/x", "/api"])
def test_unknown_api_paths_are_404_for_every_method(client, method, path):
    """Regression: the SPA route used to claim /api paths, turning these into 405s."""
    response = client.request(method, path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_head_on_get_only_api_route_is_not_reported_missing(client):
    """Regression: HEAD /api/health used to be swallowed by the SPA route and return 404."""
    assert client.head("/api/health").status_code == 405


def test_wrong_method_on_api_route_is_still_405(client):
    assert client.post("/api/health").status_code == 405


def test_api_docs_and_schema_still_served(client):
    assert client.get("/api/docs").status_code == 200
    schema = client.get("/api/openapi.json").json()
    assert "/api/health" in schema["paths"]
    assert not any(not p.startswith("/api") for p in schema["paths"])


# --- Without a build --------------------------------------------------------------------


def test_without_built_frontend_only_the_api_is_served(tmp_path):
    client = TestClient(create_app(frontend_dist=tmp_path / "does-not-exist"))

    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404
    assert client.get("/research").status_code == 404


def test_default_dist_path_is_absolute_and_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo_root = Path(main_module.__file__).resolve().parents[2]

    assert DEFAULT_FRONTEND_DIST.is_absolute()
    assert DEFAULT_FRONTEND_DIST == repo_root / "frontend" / "dist"


def test_index_html_requested_directly_is_not_cached(client):
    """Regression: /index.html served as a plain file had no Cache-Control after a deploy."""
    response = client.get("/index.html")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
