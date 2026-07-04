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


async def _upload(token_access: str, *, kind: str = "image") -> str:
    """Пройти двухшаговую загрузку и вернуть media-token.

    Шаг 1: ``POST /media/upload`` — проверка прав, выдача одноразового upload-token.
    Шаг 2: ``POST /media/upload/{upload_token}`` — приём файла, постановка в очередь.

    :arg token_access: access-JWT загружающего пользователя.
    :arg kind: вид медиа (image|video|icon|avatar).
    :return: media-token для опроса статуса/выдачи.
    """
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r1 = await mw.post(
            "/media/upload",
            params={"kind": kind},
            headers={"Authorization": f"Bearer {token_access}"},
        )
        assert r1.status_code == 201, r1.text
        upload_token = r1.json()["upload_token"]

        r2 = await mw.post(
            f"/media/upload/{upload_token}",
            content=_PNG,
            headers={
                "Authorization": f"Bearer {token_access}",
                "Content-Type": "image/png",
            },
        )
    assert r2.status_code == 202, r2.text
    body = r2.json()
    assert body["status"] == "queued"
    return body["token"]


async def test_media_upload_convert_register(http, new_user):
    token_access = await _access(new_user)
    token = await _upload(token_access)

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
        r = await mw.post("/media/upload", params={"kind": "image"})
    assert r.status_code == 401, r.text


async def test_admin_media_list_and_cleanup(http, new_user, seed):
    token_access = await _access(new_user)
    token = await _upload(token_access)

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
    entry = next((m for m in lst.json() if m["token"] == token), None)
    assert entry is not None
    # mediaworker записал варианты (полный webp + обрезанный мини-webp).
    assert "main" in entry["variants"]
    assert "thumb" in entry["variants"]
    assert entry["variants"]["thumb"]["url"] == f"/media/{token}.thumb"

    # чистка орфанов (медиа не привязано ни к товару, ни к аватарке)
    cl = await http.post("/api/v1/admin/media/cleanup", headers=hdr)
    assert cl.status_code == 200, cl.text
    assert cl.json()["deleted"] >= 1


async def _state(http, token: str) -> str:
    resp = await http.get(f"/api/v1/media/status/{token}")
    return resp.json().get("state")
