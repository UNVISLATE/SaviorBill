"""Админ: управление медиа (/api/v1/admin/media).

Удаление конкретного медиа и чистка «осиротевших» записей (не привязанных ни к
товарам-вложениям, ни к аватаркам). Файлы удаляет mediaworker по задаче в Valkey.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr, SystemMediaModel
from models.user import UserModel
from schemas.media import Media
from services.audit import audit
from utils.config import AppConfig
from utils.mediabus import MediaBus

router = APIRouter()


def _bus(request: Request, vk: valkey.Valkey) -> MediaBus:
    cfg: AppConfig = request.app.state.settings
    return MediaBus(vk, cfg.MEDIA_TASK_STREAM)


@router.get(
    "/media",
    response_model=list[Media],
    dependencies=[Depends(require_perm("media.read"))],
    summary="Media",
)
async def list_media(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> list[Media]:
    rows = await mngr.list_all(limit=limit, offset=offset)
    return [Media.from_model(m) for m in rows]


async def _drop(mngr: SystemMediaMngr, bus: MediaBus, media: SystemMediaModel) -> None:
    """Удалить запись медиа и поставить задачу удаления файла из хранилища."""
    await bus.enqueue_delete(media.backend, [media.path])
    await mngr.delete(media)


@router.delete(
    "/media/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete media",
)
async def delete_media(
    request: Request,
    media_id: int,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    acc: UserModel = Depends(require_perm("media.delete")),
) -> None:
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    await _drop(mngr, _bus(request, vk), media)
    await audit(
        mngr.s,
        action="media.delete",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="media",
        target_id=str(media_id),
        ip=request.client.host if request.client else None,
        meta={"token": media.token, "backend": media.backend},
    )
    await mngr.s.commit()


@router.post(
    "/media/cleanup",
    dependencies=[Depends(require_perm("media.cleanup"))],
    summary="Cleanup media",
    description="Delete unused media older than the grace period and queue file cleanup.",
)
async def cleanup_media(
    request: Request,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    bus = _bus(request, vk)
    grace = await settings.get_int("media.cleanup_grace_sec", 3600)
    orphans = await mngr.orphans(grace_sec=grace or 0)
    for media in orphans:
        await _drop(mngr, bus, media)
    await mngr.s.commit()
    return {"deleted": len(orphans)}


__all__ = ["router"]
