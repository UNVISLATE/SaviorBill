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

MEDIAWORKER_URL = os.environ.get("MEDIAWORKER_URL", "http://localhost:8001")

# 16x16 PNG (валидный вход для ffmpeg -> webp; 1x1 — крайний случай libwebp).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR42mM4ISdHEmIY1TCq"
    "YfhqAADkYgQQ6ZuA8QAAAABJRU5ErkJggg=="
)


async def _access(new_user) -> str:
    _login, _pwd, tokens = await new_user()
    return tokens["access_token"]


async def _upload(token_access: str, *, tag: str | None = None) -> str:
    """Пройти двухшаговую загрузку и вернуть media-token.

    Шаг 1: ``POST /api/media/upload`` — проверка прав, выдача одноразового upload-token.
    Шаг 2: ``POST /api/media/upload/{upload_token}`` — приём файла, постановка в очередь.

    :arg token_access: access-JWT загружающего пользователя.
    :arg tag: опциональная UI-метка (латиница+цифры, до 16 символов).
    :return: media-token для опроса статуса/выдачи.
    """
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r1 = await mw.post(
            "/api/media/upload",
            params={"tag": tag} if tag else {},
            headers={"Authorization": f"Bearer {token_access}"},
        )
        assert r1.status_code == 201, r1.text
        upload_token = r1.json()["upload_token"]

        r2 = await mw.post(
            f"/api/media/upload/{upload_token}",
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
    token = await _upload(token_access, tag="cover1")

    async def _status():
        resp = await http.get(f"/api/v1/media/status/{token}")
        return resp.json()

    data = await wait_until(
        _status, lambda d: d.get("state") in ("ready", "failed"), timeout=60
    )
    assert data["state"] == "ready", data
    assert data["url"] == f"/api/media/{token}"
    assert data["mime"] == "image/webp"
    assert data["tag"] == "cover1"


async def test_media_op_status_after_convert(http, new_user):
    """`worker_jobs` (см. models/worker_jobs.py) отражает финальный op-статус

    конвейера конвертации; тот же источник, что и /status/{token}, поэтому
    оба не могут "разойтись" в терминальном состоянии."""
    token_access = await _access(new_user)
    token = await _upload(token_access)

    await wait_until(
        lambda: _state(http, token), lambda s: s in ("ready", "failed"), timeout=60
    )

    resp = await http.get(f"/api/v1/media/{token}/ops/convert/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"] == token
    assert body["op"] == "convert"
    assert body["state"] == "ready"
    assert body["finished_at"] is not None


async def test_media_op_status_unknown_op(http, new_user):
    token_access = await _access(new_user)
    token = await _upload(token_access)
    resp = await http.get(f"/api/v1/media/{token}/ops/thumb_replace/status")
    assert resp.status_code == 404, resp.text


async def test_media_upload_requires_auth(new_user):
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        r = await mw.post("/api/media/upload")
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
    # mediaworker записал основной файл; для маленького тестового PNG thumb не
    # генерируется (фото меньше media.small_max_bytes — см. worker.py::_convert).
    assert entry["media"] is not None
    assert entry["thumb"] is None

    # чистка орфанов (медиа не привязано ни к товару, ни к аватарке) — грейс-период
    # по умолчанию (1 час) исключил бы только что загруженный файл, обнуляем для теста.
    await http.put(
        "/api/v1/admin/settings/raw/media.cleanup_grace_sec",
        headers=hdr,
        json={"value": "0"},
    )
    cl = await http.post("/api/v1/admin/media/cleanup", headers=hdr)
    assert cl.status_code == 200, cl.text
    assert cl.json()["deleted"] >= 1


async def _state(http, token: str) -> str:
    resp = await http.get(f"/api/v1/media/status/{token}")
    return resp.json().get("state")


async def test_mediaworker_status_includes_jobs(new_user):
    """Собственный (не billing) статус mediaworker отдаёт сводку job'ов —
    не только терминальный ``ready``/``failed``, но и что именно произошло
    (какие ffmpeg-запуски, их op/state) — см. ``api/status.py``.
    """
    token_access = await _access(new_user)
    token = await _upload(token_access, tag="jobsfield")

    async def _mw_status():
        async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
            resp = await mw.get(f"/api/media/status/{token}")
            return resp.json()

    data = await wait_until(
        _mw_status, lambda d: d.get("state") in ("ready", "failed"), timeout=60
    )
    assert data["state"] == "ready", data
    assert isinstance(data["jobs"], list) and data["jobs"], data
    job = data["jobs"][0]
    assert job["op"] == "convert"
    assert job["status"] == "ready"


async def test_mediaworker_logs_requires_perm(new_user):
    """Обычный пользователь без ``logs.read`` не должен видеть чужие job'ы."""
    token_access = await _access(new_user)
    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        resp = await mw.get(
            "/api/media/logs/jobs", headers={"Authorization": f"Bearer {token_access}"}
        )
    assert resp.status_code == 403, resp.text


async def test_mediaworker_logs_admin_can_read_job_and_progress(http, new_user, seed):
    """Админ (``logs.read``) видит список job'ов, метаданные и снимок прогресса
    напрямую через mediaworker — без прыжка через billing.
    """
    token_access = await _access(new_user)
    token = await _upload(token_access, tag="logsread")

    await wait_until(
        lambda: _state(http, token), lambda s: s in ("ready", "failed"), timeout=60
    )

    admin_login, _pwd, admin_tokens = await new_user()
    await seed.make_admin(admin_login)
    r = await http.post(
        "/api/v1/auth/login",
        json={"login": admin_login, "password": "secret123"},
    )
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

    async with httpx.AsyncClient(base_url=MEDIAWORKER_URL, timeout=30) as mw:
        jobs_resp = await mw.get("/api/media/logs/jobs?limit=50", headers=hdr)
        assert jobs_resp.status_code == 200, jobs_resp.text
        job = next((j for j in jobs_resp.json() if j.get("token") == token), None)
        assert job is not None, jobs_resp.json()

        job_resp = await mw.get(f"/api/media/logs/jobs/{job['job_id']}", headers=hdr)
        assert job_resp.status_code == 200, job_resp.text
        assert job_resp.json()["token"] == token

        progress_resp = await mw.get(
            f"/api/media/logs/jobs/{job['job_id']}/progress", headers=hdr
        )
        assert progress_resp.status_code == 200, progress_resp.text
        progress = progress_resp.json()
        assert progress.get("done") in ("1", None)  # изображение может не публиковать прогресс

        missing_resp = await mw.get(
            "/api/media/logs/jobs/does-not-exist-job-id", headers=hdr
        )
        assert missing_resp.status_code == 404, missing_resp.text

