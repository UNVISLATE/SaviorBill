"""Админ: управление медиа (/api/v1/admin/media).

Удаление конкретного медиа и чистка «осиротевших» записей (не привязанных ни к
товарам-вложениям, ни к аватаркам). Файлы удаляет mediaworker по задаче в Valkey.
"""

from __future__ import annotations

import re

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr, SystemMediaModel, all_storage_keys
from models.user import UserModel
from schemas.media import Media
from schemas.page import Page
from services.audit import audit
from core.config import AppConfig
from messaging.mediabus import MediaBus
from utils.pagination import apply_sort, paginate, q_param, sort_param
from sqlalchemy import select

router = APIRouter()

_MEDIA_SORT_FIELDS = {"id", "created_at", "size", "status", "kind", "tag"}

# До 16 символов, только латиница и цифры (см. mediaworker/src/api/upload.py::_TAG_RE
# — то же правило по обе стороны, метка задаётся при загрузке и меняется здесь).
_TAG_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


class MediaTagIn(BaseModel):
    """Тело запроса на изменение метки медиа."""

    tag: str | None = Field(
        default=None,
        max_length=16,
        description="Новая метка (латиница+цифры, до 16 символов) или null — снять",
    )


def _bus(request: Request, vk: valkey.Valkey) -> MediaBus:
    cfg: AppConfig = request.app.state.settings
    return MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY)


@router.get(
    "",
    response_model=Page[Media],
    dependencies=[Depends(require_perm("media.read"))],
    summary="Media",
    description="Все медиа (постранично), либо только владельца — фильтр "
    "`owner_id` для просмотра медиа конкретного пользователя из админского "
    "Drawer (см. IMPLEMENTATION_PLAN.md §4). `q` searches tag/mime (exact "
    f"substring); `sort` accepts {'/'.join(sorted(_MEDIA_SORT_FIELDS))}.",
)
async def list_media(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    owner_id: int | None = Query(default=None),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Page[Media]:
    stmt = mngr.stmt_for_owner(owner_id) if owner_id is not None else select(SystemMediaModel)
    stmt = apply_sort(stmt, SystemMediaModel, sort, _MEDIA_SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(SystemMediaModel.id.desc())
    if q:
        stmt = stmt.where(
            SystemMediaModel.tag.ilike(f"%{q}%") | SystemMediaModel.mime.ilike(f"%{q}%")
        )
    items, total, has_more = await paginate(
        mngr.s, stmt, Media.from_model, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset, has_more=has_more)


async def _drop(mngr: SystemMediaMngr, bus: MediaBus, media: SystemMediaModel) -> None:
    """Удалить запись медиа и поставить задачу удаления ВСЕХ файлов из хранилища
    (main + thumb + previews — иначе thumb/previews остаются мусором)."""
    await bus.enqueue_delete(media.backend, all_storage_keys(media))
    await mngr.delete(media)


@router.delete(
    "/{media_id}",
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


@router.put(
    "/{media_id}/tag",
    response_model=Media,
    summary="Update media tag",
    description="Изменить UI-метку медиа (латиница+цифры, до 16 символов).",
)
async def update_media_tag(
    request: Request,
    media_id: int,
    body: MediaTagIn,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    acc: UserModel = Depends(require_perm("media.write")),
) -> Media:
    if body.tag is not None and not _TAG_RE.match(body.tag):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "tag must be 1-16 latin letters/digits",
        )
    media = await mngr.by_id(media_id)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    await mngr.set_tag(media, body.tag)
    await audit(
        mngr.s,
        action="media.tag",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="media",
        target_id=str(media_id),
        ip=request.client.host if request.client else None,
        meta={"tag": body.tag},
    )
    await mngr.s.commit()
    return Media.from_model(media)


@router.post(
    "/cleanup",
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
