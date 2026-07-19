"""Админ: хвост журнала медиа-тасков (mediaworker пишет ``tasklog:media``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.task_log import get_task_log
from telemetry.task_log import TaskLog

router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(require_perm("tasks.read"))],
    summary="Media tasks log tail",
    description="Последние факты о медиа-тасках (convert/preview_add/"
    "thumb_replace): queued/processing/ready/failed. Пишет mediaworker, "
    "billing читает из общего Valkey напрямую (без HTTP между сервисами).",
)
async def tail_media_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail("media", limit)


__all__ = ["router"]
