"""Медиа: статус конвертации (/api/v1/media).

Приём загрузки и отдача файлов вынесены в mediaworker (через Caddy). billing
хранит только метаданные и отдаёт статус конвертации по токену.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr
from models.user import UserModel
from schemas.media import Media, MediaStatus
from utils.config import AppConfig
from utils.mediabus import MediaBus
from utils.rbac import has_perm

router = APIRouter(prefix="/api/v1/media", tags=["media"])


class PreviewOrderIn(BaseModel):
    """Тело запроса на изменение порядка previews[]."""

    order: list[int] = Field(
        description="Перестановка индексов текущего списка previews (та же "
        "длина и набор значений, что и сейчас)"
    )


async def _owned_media(mngr: SystemMediaMngr, token: str, acc: UserModel) -> object:
    """Найти медиа по токену и проверить, что запрашивающий — владелец либо
    имеет право ``media.uploadlarge``"""
    media = await mngr.by_token(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    perms = acc.role.perms if acc.role else None
    if media.owner_id != acc.id and not has_perm(perms, "media.uploadlarge"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "не владелец медиа")
    return media


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
    bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN)

    data = await bus.status(token)
    if data:
        return MediaStatus(
            token=token,
            state=data.get("state", "processing"),
            url=data.get("url") or None,
            mime=data.get("mime") or None,
            tag=data.get("tag") or None,
            error=data.get("error") or None,
        )

    # Статус в Valkey мог истечь — источник истины по готовым медиа это БД.
    media = await mngr.by_token(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return MediaStatus(
        token=token,
        state=media.status,
        url=f"/api/media/{media.token}" if media.status == "ready" else None,
        mime=media.mime,
        tag=media.tag,
    )


@router.delete(
    "/{token}/previews/{index}",
    response_model=Media,
    summary="Remove a preview",
    description="Удалить конкретное превью по индексу (только владелец медиа). "
    "Индекс — позиция в текущем previews[] на момент запроса, см. ответ.",
)
async def remove_preview(
    request: Request,
    token: str,
    index: int,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    acc: UserModel = Depends(get_current_acc),
) -> Media:
    media = await _owned_media(mngr, token, acc)
    removed = await mngr.remove_preview(media, index)
    if removed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "preview not found")
    if removed.get("key"):
        cfg: AppConfig = request.app.state.settings
        bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN)
        await bus.enqueue_delete(media.backend, [removed["key"]])
        # Убрать осиротевший ключ из кэша вариантов mediaworker (media:file:*)
        # — тот же Valkey, тот же префикс, что и в mediaworker/utils/worker.py.
        await vk.hdel(f"media:file:{token}", removed.get("name") or "")
    await mngr.s.commit()
    return Media.from_model(media)


@router.patch(
    "/{token}/previews/order",
    response_model=Media,
    summary="Reorder previews",
    description="Переставить previews[] в новом порядке (только владелец медиа).",
)
async def reorder_previews(
    token: str,
    body: PreviewOrderIn,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    acc: UserModel = Depends(get_current_acc),
) -> Media:
    media = await _owned_media(mngr, token, acc)
    ok = await mngr.reorder_previews(media, body.order)
    if not ok:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "order must be a permutation of current indices",
        )
    await mngr.s.commit()
    return Media.from_model(media)


__all__ = ["router"]
