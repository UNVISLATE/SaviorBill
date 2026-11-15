import pytest
from fastapi.testclient import TestClient

from app import app
from core.config import AppConfig


@pytest.fixture
def client():
    app.state.settings = AppConfig(DEBUG=True, DOCS_ENABLED=True)
    return TestClient(app, follow_redirects=False)


def test_api_docs_swagger_ui_default(client):
    response = client.get("/api/docs")
    assert response.status_code == 200
    html = response.text
    assert "swagger-ui-bundle.js" in html
    assert "swagger-ui.css" in html


def test_api_v1_docs_redirect(client):
    response = client.get("/api/v1/docs")
    assert response.status_code == 307
    assert response.headers["location"] == "/api/docs"


def test_api_redoc_default(client):
    response = client.get("/api/redoc")
    assert response.status_code == 200
    html = response.text
    assert "redoc.standalone.js" in html


def test_api_v1_redoc_redirect(client):
    response = client.get("/api/v1/redoc")
    assert response.status_code == 307
    assert response.headers["location"] == "/api/redoc"


def test_health_check_debug_flag(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "debug" in data
    assert data["debug"] is True
    assert "docs_enabled" in data
    assert data["docs_enabled"] is True


def test_api_docs_disabled(client):
    app.state.settings = AppConfig(DOCS_ENABLED=False)
    resp_docs = client.get("/api/docs")
    assert resp_docs.status_code == 404
    resp_redoc = client.get("/api/redoc")
    assert resp_redoc.status_code == 404
    app.state.settings = AppConfig(DEBUG=True, DOCS_ENABLED=True)
