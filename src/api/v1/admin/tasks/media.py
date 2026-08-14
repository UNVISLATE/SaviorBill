"""Админ: хвост журнала медиа-тасков (mediaworker пишет ``tasklog:media``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.task_log import get_task_log
from telemetry.task_log import TaskLog

router = APIRouter()


@router.get(
    "/summary",
    dependencies=[Depends(require_perm("system.tasks.summary.read"))],
    summary="Media tasks log tail (sanitized)",
    description="То же самое, что обычный tail, но без `detail`/`trace_id` — "
    "для операторов, которым не нужна внутренняя диагностика ошибок.",
)
async def tail_media_tasks_summary(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail_summary("media", limit)


@router.get(
    "",
    dependencies=[Depends(require_perm("system.tasks.tail.read"))],
    summary="Media tasks log tail",
    description="Последние факты о медиа-тасках (convert/preview_add/"
    "thumb_replace): queued/processing/ready/failed. Пишет mediaworker, "
    "billing читает из общего Valkey напрямую (без HTTP между сервисами). "
    "Содержит сырой `detail` (часто = текст исключения) и `trace_id` — "
    "отдельное от summary право (см. AUDIT.md §3.6).",
)
async def tail_media_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail("media", limit)


__all__ = ["router"]
