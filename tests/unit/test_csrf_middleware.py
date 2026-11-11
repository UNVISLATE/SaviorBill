"""Юнит-тесты CSRF defense-in-depth поверх cookie-авторизации."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from security.csrf import CookieCSRFMiddleware, _is_exempt, _origin_allowed, _origin_of
from security.sec.cookies import ACCESS_COOKIE

pytestmark = pytest.mark.unit


def test_origin_of_strips_path_from_referer():
    assert _origin_of("https://admin.example.com/login?x=1") == "https://admin.example.com"


def test_origin_of_passthrough_for_bare_origin():
    assert _origin_of("https://admin.example.com") == "https://admin.example.com"


def test_origin_allowed_matches_ignoring_trailing_slash():
    assert _origin_allowed("https://admin.example.com/", ["https://admin.example.com"])
    assert not _origin_allowed("https://evil.com", ["https://admin.example.com"])


def test_is_exempt_helper():
    assert _is_exempt("/api/v1/auth/login")
    assert _is_exempt("/api/v1/auth/register")
    assert _is_exempt("/api/v1/auth/refresh")
    assert _is_exempt("/api/v1/auth/logout")
    assert _is_exempt("/api/v1/auth/password/reset/request")
    assert _is_exempt("/api/v1/auth/password/reset/confirm")
    assert _is_exempt("/api/v1/callback/pay/crypto")
    assert not _is_exempt("/api/v1/user/me/password")
    assert not _is_exempt("/api/v1/admin/users")


class _FakeCfg:
    def __init__(
        self,
        origins: list[str],
        public_url: str | None = None,
        domain: str = "",
    ) -> None:
        self.cors_origins_list = origins
        self.PUBLIC_URL = public_url
        self.DOMAIN = domain


async def _ok(request):
    return JSONResponse({"ok": True})


def _make_app(
    origins: list[str],
    public_url: str | None = None,
    domain: str = "",
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/x", _ok, methods=["GET", "POST"]),
            Route("/api/v1/auth/login", _ok, methods=["POST"]),
            Route("/api/v1/callback/pay/test", _ok, methods=["POST"]),
        ]
    )
    app.add_middleware(
        CookieCSRFMiddleware,
        cfg=_FakeCfg(origins, public_url=public_url, domain=domain),
    )
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


def test_empty_cors_origins_rejects_foreign_origin_and_allows_same_origin():
    """При пустом CORS_ORIGINS разрешается same-origin (Host/PUBLIC_URL/DOMAIN), а чужой Origin отклоняется."""
    client = TestClient(_make_app([], public_url="https://shop.example.com", domain="api.example.com"))

    # Чужой origin — отклонён даже при пустом CORS_ORIGINS
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "http://127.0.0.1:5173"}
    )
    assert resp.status_code == 403

    # Same-origin по Host заголовку TestClient (http://testserver) — разрешён
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "http://testserver"}
    )
    assert resp.status_code == 200

    # PUBLIC_URL / DOMAIN — разрешены
    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "https://shop.example.com"}
    )
    assert resp.status_code == 200

    resp = client.post(
        "/x", cookies={ACCESS_COOKIE: "tok"}, headers={"Origin": "https://api.example.com"}
    )
    assert resp.status_code == 200

    # Dev Vite proxy (Origin: localhost:5173 -> Host: 127.0.0.1:8000): оба loopback — разрешён,
    # но внешний origin на loopback Host всё равно отклоняется.
    resp_dev = client.post(
        "/x",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Origin": "http://localhost:5173", "Host": "127.0.0.1:8000"},
    )
    assert resp_dev.status_code == 200

    resp_dev_evil = client.post(
        "/x",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Origin": "https://evil.com", "Host": "127.0.0.1:8000"},
    )
    assert resp_dev_evil.status_code == 403


def test_exempt_endpoints_allowed_even_with_cookie_and_no_origin():
    """Эндпоинты входа и вебхуков не должны блокироваться из-за остаточных кук."""
    client = TestClient(_make_app(["https://admin.example.com"]))
    # Логин с кукой в клиенте и без Origin
    resp = client.post("/api/v1/auth/login", cookies={ACCESS_COOKIE: "stale_token"})
    assert resp.status_code == 200

    # Вебхук колбэка с кукой и без Origin
    resp = client.post("/api/v1/callback/pay/test", cookies={ACCESS_COOKIE: "stale_token"})
    assert resp.status_code == 200
