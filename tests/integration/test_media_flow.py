"""Интеграционные тесты медиа-подсистемы: upload -> convert -> register -> статус.

Загрузка идёт напрямую в mediaworker (в проде — через Caddy), статус и список
медиа — через billing. Проверяем весь конвейер на маленьком PNG (ffmpeg -> webp).
"""

import base64
import os

import httpx
import pytest

from conftest import wait_until

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MEDIAWORKER_URL = os.environ.get("MEDIAWORKER_URL", "http://localhost:8080")

# 16x16 PNG (валидный вход для ffmpeg -> webp; 1x1 — крайний случай libwebp).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR42mM4ISdHEmIY1TCq"
    "YfhqAADkYgQQ6ZuA8QAAAABJRU5ErkJggg=="
)


async def _access(new_user) -> str:
    _login, _pwd, tokens = await new_user()
    return tokens["access_token"]


async def test_media_upload_convert_register(http, new_user):
    token_access = await _access(new_user)
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r = await mw.post(
            "/media/upload",
            params={"kind": "image"},
            content=_PNG,
            headers={
                "Authorization": f"Bearer {token_access}",
                "Content-Type": "image/png",
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["token"]
    assert body["status"] == "processing"

    async def _status():
        resp = await http.get(f"/api/v1/media/status/{token}")
        return resp.json()

    data = await wait_until(
        _status, lambda d: d.get("state") in ("ready", "failed"), timeout=60
    )
    assert data["state"] == "ready", data
    assert data["url"] == f"/media/{token}"
    assert data["mime"] == "image/webp"


async def test_media_upload_requires_auth(new_user):
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r = await mw.post("/media/upload", params={"kind": "image"}, content=_PNG)
    assert r.status_code == 401, r.text


async def test_admin_media_list_and_cleanup(http, new_user, seed):
    token_access = await _access(new_user)
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r = await mw.post(
            "/media/upload",
            params={"kind": "image"},
            content=_PNG,
            headers={
                "Authorization": f"Bearer {token_access}",
                "Content-Type": "image/png",
            },
        )
    assert r.status_code == 201, r.text
    token = r.json()["token"]

    await wait_until(
        lambda: _state(http, token),
        lambda s: s in ("ready", "failed"),
        timeout=60,
    )

    admin_login, _pwd, admin_tokens = await new_user()
    await seed.make_admin(admin_login)
    # переавторизуемся, чтобы токен нёс админ-роль
    r = await http.post(
        "/api/v1/auth/login",
        json={"login": admin_login, "password": "secret123"},
    )
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

    lst = await http.get("/api/v1/admin/media", headers=hdr)
    assert lst.status_code == 200, lst.text
    assert any(m["token"] == token for m in lst.json())

    # чистка орфанов (медиа не привязано ни к товару, ни к аватарке)
    cl = await http.post("/api/v1/admin/media/cleanup", headers=hdr)
    assert cl.status_code == 200, cl.text
    assert cl.json()["deleted"] >= 1


async def _state(http, token: str) -> str:
    resp = await http.get(f"/api/v1/media/status/{token}")
    return resp.json().get("state")
