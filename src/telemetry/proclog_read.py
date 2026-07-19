"""Billing-side чтение ``proclog:*`` — сырой лог ffmpeg/ffprobe, который пишет
mediaworker (``mediaworker/src/utils/proclog.py``) в общий Valkey.

Billing и mediaworker сознательно не делят код (см. прецедент
``task_log.py``/``telemetry.py``) — здесь только чтение по тому же
ключевому контракту, без записи (пишет исключительно mediaworker).
"""

from __future__ import annotations

import valkey.asyncio as valkey

_JOBS_KEY = "proclog:jobs"
_META_PREFIX = "proclog:meta:"
_LINES_PREFIX = "proclog:lines:"
_EVENTS_PREFIX = "proclog:events:"


def events_channel(job_id: str) -> str:
    return f"{_EVENTS_PREFIX}{job_id}"


async def tail(vk: valkey.Valkey, job_id: str) -> list[str]:
    """Весь накопленный сырой вывод job'а (в хронологическом порядке)."""
    return await vk.lrange(f"{_LINES_PREFIX}{job_id}", 0, -1)


async def recent_jobs(vk: valkey.Valkey, limit: int = 50) -> list[dict]:
    """Метаданные последних запусков ffmpeg/ffprobe (для листинга в админке)."""
    ids = await vk.lrange(_JOBS_KEY, 0, limit - 1)
    out: list[dict] = []
    for job_id in ids:
        meta = await vk.hgetall(f"{_META_PREFIX}{job_id}")
        if meta:
            out.append({"job_id": job_id, **meta})
    return out


async def get_job(vk: valkey.Valkey, job_id: str) -> dict | None:
    """Метаданные одного запуска ffmpeg/ffprobe (REST single-статус job'а)."""
    meta = await vk.hgetall(f"{_META_PREFIX}{job_id}")
    if not meta:
        return None
    return {"job_id": job_id, **meta}


__all__ = ["tail", "recent_jobs", "get_job", "events_channel"]
