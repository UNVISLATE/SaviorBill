"""Юнит-тесты CSRF defense-in-depth поверх cookie-авторизации."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from security.csrf import CookieCSRFMiddleware, _origin_allowed, _origin_of
from security.sec.cookies import ACCESS_COOKIE

pytestmark = pytest.mark.unit


def test_origin_of_strips_path_from_referer():
    assert _origin_of("https://admin.example.com/login?x=1") == "https://admin.example.com"


def test_origin_of_passthrough_for_bare_origin():
    assert _origin_of("https://admin.example.com") == "https://admin.example.com"


def test_origin_allowed_matches_ignoring_trailing_slash():
    assert _origin_allowed("https://admin.example.com/", ["https://admin.example.com"])
    assert not _origin_allowed("https://evil.com", ["https://admin.example.com"])


class _FakeCfg:
    def __init__(self, origins: list[str]) -> None:
        self.cors_origins_list = origins


async def _ok(request):
    return JSONResponse({"ok": True})


def _make_app(origins: list[str]) -> Starlette:
    app = Starlette(routes=[Route("/x", _ok, methods=["GET", "POST"])])
    app.add_middleware(CookieCSRFMiddleware, cfg=_FakeCfg(origins))
    return app


def test_get_request_never_blocked():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.get("/x", cookies={ACCESS_COOKIE: "tok"})
    assert resp.status_code == 200


def test_post_with_bearer_header_skips_check():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.post(
        "/x",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Authorization": "Bearer x", "Origin": "https://evil.com"},
    )
    assert resp.status_code == 200


def test_post_without_cookie_skips_check():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.post("/x", headers={"Origin": "https://evil.com"})
    assert resp.status_code == 200


def test_post_with_cookie_and_matching_origin_allowed():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "https://admin.example.com"}
    )
    assert resp.status_code == 200


def test_post_with_cookie_and_foreign_origin_rejected():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "https://evil.com"}
    )
    assert resp.status_code == 403


def test_post_with_cookie_and_no_origin_rejected():
    client = TestClient(_make_app(["https://admin.example.com"]))
    resp = client.post("/x", cookies={ACCESS_COOKIE: "tok"})
    assert resp.status_code == 403


def test_no_allowed_origins_configured_allows_any_origin():
    """CORS_ORIGINS не задан (same-origin/dev через прокси) — проверка по origin не блокирует."""
    client = TestClient(_make_app([]))
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "http://127.0.0.1:5173"}
    )
    assert resp.status_code == 200
