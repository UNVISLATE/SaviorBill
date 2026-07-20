"""Собственные загрузки медиа текущего пользователя (/api/v1/user/media)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from core.config import AppConfig
from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from messaging.mediabus import MediaBus
from models.service_attachment import ServiceAttachmentModel
from models.system_media import SystemMediaMngr, all_storage_keys
from models.user import UserModel
from schemas.media import Media
from schemas.page import Page
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/media",
    response_model=Page[Media],
    summary="My uploaded media",
    description=(
        "Own uploads (any status: processing/ready/error), newest first. "
        "Counts toward user.media.limit — see docs/media.md."
    ),
    dependencies=[Depends(require_perm("user.media.read"))],
)
async def my_media(
    pp: PageParams = Depends(page_params),
    acc: UserModel = Depends(get_current_acc),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Page[Media]:
    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_for_owner(acc.id),
        Media.from_model,
        limit=pp.limit,
        offset=pp.offset,
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.delete(
    "/media/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete own media",
    description=(
        "Deletes an own upload and its files (main/thumb/previews). If it is "
        "currently the account's avatar, the avatar is cleared first. If it "
        "is still attached to a service order, deletion is refused (409) — "
        "remove the attachment there first."
    ),
    dependencies=[Depends(require_perm("user.media.delete"))],
)
async def delete_my_media(
    request: Request,
    token: str,
    acc: UserModel = Depends(get_current_acc),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> None:
    media = await mngr.by_token(token)
    # 404 для "не найдено" и "не моё" одинаковы — иначе можно перебором узнать
    # существующие токены чужих медиа (см. AUDIT.md §2.1, тот же принцип, что
    # и в set_avatar/_owned_media).
    if media is None or media.owner_id != acc.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")

    attached = await mngr.s.scalar(
        select(ServiceAttachmentModel.id)
        .where(ServiceAttachmentModel.media_id == media.id)
        .limit(1)
    )
    if attached is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "media is attached to a service order — remove the attachment first",
        )

    if acc.avatar_media_id == media.id:
        acc.avatar_media_id = None
        await mngr.s.flush()

    cfg: AppConfig = request.app.state.settings
    bus = MediaBus(
        vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY
    )
    await bus.enqueue_delete(media.backend, all_storage_keys(media))
    await mngr.delete(media)
    await mngr.s.commit()


__all__ = ["router"]
