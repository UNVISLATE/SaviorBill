"""Медиа: статус конвертации (/api/v1/media).

Приём загрузки и отдача файлов вынесены в mediaworker (через Caddy). billing
хранит только метаданные и отдаёт статус конвертации по токену.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.media import get_media_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr
from schemas.media import MediaStatus
from utils.config import AppConfig
from utils.mediabus import MediaBus

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get(
    "/status/{token}",
    response_model=MediaStatus,
    summary="Media status",
    description="Returns the processing status for uploaded media by token.",
)
async def media_status(
    request: Request,
    token: str,
    vk: valkey.Valkey = Depends(get_valkey_client),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> MediaStatus:
    cfg: AppConfig = request.app.state.settings
    bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM)

    data = await bus.status(token)
    if data:
        return MediaStatus(
            token=token,
            state=data.get("state", "processing"),
            url=data.get("url") or None,
            mime=data.get("mime") or None,
            error=data.get("error") or None,
        )

    # Статус в Valkey мог истечь — источник истины по готовым медиа это БД.
    media = await mngr.by_token(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return MediaStatus(
        token=token,
        state=media.status,
        url=f"/media/{media.token}" if media.status == "ready" else None,
        mime=media.mime,
    )


__all__ = ["router"]
