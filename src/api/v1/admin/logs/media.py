"""Админ: список последних запусков ffmpeg/ffprobe для realtime-логов.

Сами логи отдаются через WS (``/apiws/v1/logs/media/{job_id}``, xterm.js);
этот REST-роут — только листинг, чтобы UI знал, какие ``job_id`` доступны
"прямо сейчас" (или недавно завершились).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from utils import proclog_read

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


__all__ = ["router"]
