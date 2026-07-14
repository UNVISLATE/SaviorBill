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

Роут зарегистрирован ДО ``serve_router`` (см. ``api/__init__.py``) — иначе
``GET /{token}`` (catch-all) перехватил бы ``/status/{token}`` так же, как это
уже случилось бы с ``/kinds``.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter()

_STATUS_PREFIX = "media:status:"


@router.get("/status/{token}")
async def media_status(request: Request, token: str) -> dict:
    vk: valkey.Valkey = request.app.state.vk
    data = await vk.hgetall(f"{_STATUS_PREFIX}{token}")
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return {
        "token": token,
        "state": data.get("state", "processing"),
        "url": data.get("url") or None,
        "mime": data.get("mime") or None,
        "tag": data.get("tag") or None,
        "error": data.get("error") or None,
    }


__all__ = ["router"]
