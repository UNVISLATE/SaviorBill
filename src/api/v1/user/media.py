"""Собственные загрузки медиа текущего пользователя (/api/v1/user/media)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field
from sqlalchemy import select

from core.config import AppConfig
from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from messaging.mediabus import MediaBus
from models.service_attachment import ServiceAttachmentModel
from models.system_media import SystemMediaMngr, all_storage_keys
from models.user import UserModel
from models.worker_jobs import WorkerJobsMngr
from schemas.media import Media, OpStatus
from schemas.page import Page
from security.rbac import has_perm
from utils.pagination import PageParams, page_params, paginate
from dependencies.media import get_worker_jobs_mngr

router = APIRouter()

# Права, снимающие лимит user.media.limit — те же, что и в mediaworker
# (см. mediaworker/src/api/upload.py::_PERM_LARGE + admin.media.upload).
_UNLIMITED_PERMS = ("media.uploadlarge", "admin.media.upload")


class MyMediaPage(Page[Media]):
    """Страница собственных медиа + текущая квота (для UI: "3 из 5")."""

    quota_limit: int | None = Field(
        default=None,
        description="Max media files for this account, or null if unlimited "
        "(media.uploadlarge/admin.media.upload perms lift the limit)",
    )


@router.get(
    "/media",
    response_model=MyMediaPage,
    summary="My uploaded media",
    description=(
        "Own uploads (any status: processing/ready/error), newest first. "
        "Counts toward user.media.limit — see docs/media.md."
    ),
    dependencies=[Depends(require_perm("user.media.read"))],
)
async def my_media(
    request: Request,
    pp: PageParams = Depends(page_params),
    acc: UserModel = Depends(get_current_acc),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> MyMediaPage:
    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_for_owner(acc.id),
        Media.from_model,
        limit=pp.limit,
        offset=pp.offset,
    )
    perms = acc.role.perms if acc.role else None
    quota_limit = None
    if not any(has_perm(perms, p) for p in _UNLIMITED_PERMS):
        cfg: AppConfig = request.app.state.settings
        quota_limit = await settings.get_int("user.media.limit", cfg.USER_MEDIA_LIMIT)
    return MyMediaPage(
        items=items,
        total=total,
        limit=pp.limit,
        offset=pp.offset,
        has_more=has_more,
        quota_limit=quota_limit,
    )


@router.get(
    "/media/jobs",
    response_model=list[OpStatus],
    summary="My active media jobs",
    description=(
        "Активные (queued/processing/retrying) джобы конвертации/пост-обработки "
        "своих загрузок — восстановление карточек 'в обработке' после "
        "перезагрузки страницы (WS /api/media/mine покрывает live-обновления, "
        "но не переживает reload сам по себе, см. IMPLEMENTATION_PLAN.md §3.Д)."
    ),
    dependencies=[Depends(require_perm("user.media.read"))],
)
async def my_media_jobs(
    acc: UserModel = Depends(get_current_acc),
    jobs: WorkerJobsMngr = Depends(get_worker_jobs_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> list[OpStatus]:
    active = await jobs.active_for_owner(acc.id)
    bus = MediaBus(vk)
    result: list[OpStatus] = []
    for job in active:
        snap = await bus.status(job.subject_key) or {}
        result.append(
            OpStatus(
                token=job.subject_key,
                op=job.op,
                state=job.state,
                attempt=job.attempt,
                error=job.error,
                created_at=job.created_at.isoformat() if job.created_at else None,
                started_at=job.started_at.isoformat() if job.started_at else None,
                finished_at=job.finished_at.isoformat() if job.finished_at else None,
                percent=float(snap["percent"]) if snap.get("percent") else None,
                eta_sec=float(snap["eta_sec"]) if snap.get("eta_sec") else None,
            )
        )
    return result


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
