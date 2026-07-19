"""Статус конвертации напрямую в mediaworker (``GET /api/media/status/{token}``).

Раньше статус был доступен только через billing
(``GET /api/v1/media/status/{token}``, читает тот же Valkey-ключ + фоллбэк на
БД). Этот роут нужен, если клиент по какой-то причине общается с mediaworker
напрямую (без billing в цепочке) — например, тот же домен смонтирован под
``/api/media/*`` отдельно от billing.

В отличие от billing-варианта здесь нет фоллбэка на Postgres: mediaworker не
владеет схемой ``system_media`` и не пишет туда статус сам, поэтому если ключ
``media:status:{token}`` протух в Valkey (``MEDIA_STATUS_TTL``) — честный 404
(источник истины по готовым медиа — billing, обращайтесь через него).

``jobs`` — сводка недавних/активных запусков ffmpeg этого токена (см.
``utils/proclog.py::jobs_for_token``): ``job_id``/``op``/``status``/``percent``/
``eta_sec``. Billing этого не отдаёт и не обязан — это ephemeral debug-данные
самого mediaworker, а не часть его контракта "готово/не готово" (см.
``docs/media.md``, раздел про realtime-лог и прогресс).

Роут зарегистрирован ДО ``serve_router`` (см. ``api/__init__.py``) — иначе
``GET /{token}`` (catch-all) перехватил бы ``/status/{token}`` так же, как это
уже случилось бы с ``/kinds``.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, status

from utils.keys import status_key
from utils.proclog import ProcLog

router = APIRouter()


@router.get("/status/{token}")
async def media_status(request: Request, token: str) -> dict:
    vk: valkey.Valkey = request.app.state.vk
    data = await vk.hgetall(status_key(token))
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    proc_log: ProcLog = request.app.state.proc_log
    return {
        "token": token,
        "state": data.get("state", "processing"),
        "url": data.get("url") or None,
        "mime": data.get("mime") or None,
        "tag": data.get("tag") or None,
        "error": data.get("error") or None,
        "jobs": await proc_log.jobs_for_token(token),
    }


__all__ = ["router"]
