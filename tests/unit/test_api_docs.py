import pytest
from fastapi.testclient import TestClient

from app import app
from core.config import AppConfig


@pytest.fixture
def client():
    # Make sure app.state.settings is set
    app.state.settings = AppConfig(DEBUG=True, DOCS_ENABLED=True)
    return TestClient(app, follow_redirects=False)


def test_api_docs_swagger_ui_custom_theme(client):
    response = client.get("/api/docs")
    assert response.status_code == 200
    html = response.text
    # Should contain Swagger UI bundle
    assert "swagger-ui-bundle.js" in html
    # Should contain custom Dark CSS
    assert "--sb-primary: #009080" in html
    assert "--sb-bg: #0b0d10" in html
    # Should contain custom SaviorBill header
    assert "sb-docs-header" in html
    assert "SaviorBill" in html
    assert "/api/redoc" in html


def test_api_v1_docs_redirect(client):
    response = client.get("/api/v1/docs")
    assert response.status_code == 307
    assert response.headers["location"] == "/api/docs"


def test_api_redoc_custom_theme(client):
    response = client.get("/api/redoc")
    assert response.status_code == 200
    html = response.text
    assert "redoc.standalone.js" in html
    assert "--sb-primary" in html or "#009080" in html
    assert "sb-docs-header" in html


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
    # Restore
    app.state.settings = AppConfig(DEBUG=True, DOCS_ENABLED=True)
