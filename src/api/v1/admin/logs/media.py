"""Админ: список последних запусков ffmpeg/ffprobe для realtime-логов.

Сами логи отдаются через WS (``/apiws/v1/logs/media/{job_id}``, xterm.js);
этот REST-роут — только листинг, чтобы UI знал, какие ``job_id`` доступны
"прямо сейчас" (или недавно завершились).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from telemetry import proclog_read

router = APIRouter()


@router.get(
    "/jobs",
    dependencies=[Depends(require_perm("logs.read"))],
    summary="Recent ffmpeg/ffprobe jobs",
    description="Последние запуски ffmpeg/ffprobe в mediaworker (job_id + "
    "op/token/state/started_at/finished_at) — используйте job_id для "
    "подключения к WS /apiws/v1/logs/media/{job_id} с реалтайм-выводом "
    "процесса (xterm.js).",
)
async def recent_media_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    vk=Depends(get_valkey_client),
) -> list[dict]:
    return await proclog_read.recent_jobs(vk, limit)


@router.get(
    "/jobs/{job_id}",
    dependencies=[Depends(require_perm("logs.read"))],
    summary="Single ffmpeg/ffprobe job status",
    description="Метаданные одного запуска ffmpeg/ffprobe (без выхода "
    "процесса — сырой вывод см. WS /apiws/v1/logs/media/{job_id}).",
)
async def media_job(
    job_id: str,
    vk=Depends(get_valkey_client),
) -> dict:
    job = await proclog_read.get_job(vk, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


__all__ = ["router"]
