"""Юнит-тесты CSRF defense-in-depth для mediaworker."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from utils.authctx import ACCESS_COOKIE
from utils.csrf import CookieCSRFMiddleware


class _FakeCfg:
    def __init__(
        self,
        origins: list[str],
        public_url: str | None = None,
        media_public_url: str | None = None,
    ) -> None:
        self.cors_origins_list = origins
        self.PUBLIC_URL = public_url
        self.MEDIA_PUBLIC_URL = media_public_url


async def _ok(request):
    return JSONResponse({"ok": True})


def _make_app(
    origins: list[str],
    public_url: str | None = None,
    media_public_url: str | None = None,
) -> Starlette:
    app = Starlette(routes=[Route("/api/media/upload", _ok, methods=["POST"])])
    app.add_middleware(
        CookieCSRFMiddleware,
        cfg=_FakeCfg(
            origins, public_url=public_url, media_public_url=media_public_url
        ),
    )
    return app


def test_empty_cors_origins_rejects_foreign_origin():
    client = TestClient(_make_app([], media_public_url="https://media.example.com"))
    resp = client.post(
        "/api/media/upload",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Origin": "https://evil.com"},
    )
    assert resp.status_code == 403


def test_empty_cors_origins_allows_same_host_and_media_public_url():
    client = TestClient(_make_app([], media_public_url="https://media.example.com"))
    resp_same = client.post(
        "/api/media/upload",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Origin": "http://testserver"},
    )
    assert resp_same.status_code == 200

    resp_media = client.post(
        "/api/media/upload",
        cookies={ACCESS_COOKIE: "tok"},
        headers={"Origin": "https://media.example.com"},
    )
    assert resp_media.status_code == 200
