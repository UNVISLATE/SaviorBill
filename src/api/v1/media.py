"""Медиа: статус конвертации (/api/v1/media).

Приём загрузки и отдача файлов вынесены в mediaworker (через Caddy). billing
хранит только метаданные и отдаёт статус конвертации по токену.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr, get_worker_jobs_mngr
from dependencies.valkey import get_valkey_client
from models.system_media import SystemMediaMngr
from models.worker_jobs import WorkerJobsMngr
from models.user import UserModel
from schemas.media import Media, MediaStatus, OpStatus
from core.config import AppConfig
from messaging.mediabus import MediaBus
from security.rbac import has_perm

router = APIRouter(prefix="/api/v1/media", tags=["media"])


class PreviewOrderIn(BaseModel):
    """Тело запроса на изменение порядка previews[]."""

    order: list[int] = Field(
        description="Перестановка индексов текущего списка previews (та же "
        "длина и набор значений, что и сейчас)"
    )


async def _owned_media(mngr: SystemMediaMngr, token: str, acc: UserModel) -> object:
    """Найти медиа по токену и проверить, что запрашивающий — владелец либо
    имеет право ``admin.media.manage_any`` (доступ к чужому медиа отдельно
    от ``media.uploadlarge``, который только про лимит размера)."""
    media = await mngr.by_token(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    perms = acc.role.perms if acc.role else None
    if media.owner_id != acc.id and not has_perm(perms, "admin.media.manage_any"):
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
    jobs: WorkerJobsMngr = Depends(get_worker_jobs_mngr),
) -> MediaStatus:
    cfg: AppConfig = request.app.state.settings
    bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY)

    # Валкей — быстрый кэш для частого поллинга сразу после аплоада; не
    # протухнет — ниже authoritative worker_jobs (БД), а не Валкей.
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

    # Кэш истёк/не создавался — authoritative источник: worker_jobs (БД), не
    # protuхает и одинаков для этого роута и для списков (см. models/worker_jobs.py).
    job = await jobs.latest("media", token, op="convert")
    media = await mngr.by_token(token)
    if job is not None and job.state not in ("ready",):
        return MediaStatus(
            token=token,
            state=job.state,
            url=None,
            mime=media.mime if media else None,
            tag=media.tag if media else None,
            error=job.error,
        )
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return MediaStatus(
        token=token,
        state=media.status,
        url=f"/api/media/{media.token}" if media.status == "ready" else None,
        mime=media.mime,
        tag=media.tag,
        error=job.error if job is not None else None,
    )


@router.get(
    "/{token}/ops/{op}/status",
    response_model=OpStatus,
    summary="Media sub-operation status",
    description="Status of a media sub-operation (preview_add/thumb_replace/...) "
    "started after the main upload/convert (see GET /status/{token} for that).",
)
async def media_op_status(
    token: str,
    op: str,
    jobs: WorkerJobsMngr = Depends(get_worker_jobs_mngr),
) -> OpStatus:
    job = await jobs.latest("media", token, op=op)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return OpStatus(
        token=token,
        op=op,
        state=job.state,
        attempt=job.attempt,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
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
        bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY)
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
