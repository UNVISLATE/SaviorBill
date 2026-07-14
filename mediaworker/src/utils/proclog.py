"""Журнал сырого вывода ffmpeg/ffprobe (mediaworker) для realtime-логов в UI.

Отдельно от ``task_log.py`` (структурированные факты о статусах тасков):
здесь хранится именно **сырой текст**, который печатает сам процесс
(включая прогресс-строки с ``\\r`` без ``\\n``) — чтобы админ мог смотреть
за ним в реальном времени через xterm.js, как за обычным терминалом.

Схема хранения в Valkey

- ``proclog:jobs`` — список последних ``max_jobs`` job_id (кольцевой буфер,
  ``LPUSH``+``LTRIM``) — для листинга "какие запуски были недавно".
- ``proclog:meta:{job_id}`` — hash с метаданными запуска (``op``, ``token``,
  ``state``, ``started_at``, ``finished_at``), TTL = ``ttl``.
- ``proclog:lines:{job_id}`` — список кусков сырого вывода в хронологическом
  порядке (``RPUSH``), TTL = ``ttl`` — для отдачи бэклога при подключении.
- ``proclog:events:{job_id}`` — Pub/Sub канал, каждый кусок публикуется как
  есть (plain text) для live-форвардинга через WS.

Один job_id — один запуск ffmpeg/ffprobe (не один token медиа): для одного
token может параллельно идти и конвертация, и генерация доп. превью — у
каждой свой job_id и свой независимый лог.
"""

from __future__ import annotations

import time
import uuid

import valkey.asyncio as valkey

_JOBS_KEY = "proclog:jobs"
_META_PREFIX = "proclog:meta:"
_LINES_PREFIX = "proclog:lines:"
_EVENTS_PREFIX = "proclog:events:"


class ProcLog:
    """Журнал сырого вывода процессов ffmpeg/ffprobe."""

    def __init__(self, vk: valkey.Valkey, max_jobs: int = 50, ttl: int = 3600) -> None:
        self.vk = vk
        self.max_jobs = max_jobs
        self.ttl = ttl

    async def start_job(self, *, op: str, token: str) -> str:
        """Зарегистрировать новый запуск; вернуть его ``job_id``."""
        job_id = uuid.uuid4().hex
        meta_key = f"{_META_PREFIX}{job_id}"
        await self.vk.hset(
            meta_key,
            mapping={"op": op, "token": token, "state": "running", "started_at": time.time()},
        )
        await self.vk.expire(meta_key, self.ttl)
        await self.vk.lpush(_JOBS_KEY, job_id)
        await self.vk.ltrim(_JOBS_KEY, 0, self.max_jobs - 1)
        return job_id

    async def finish_job(self, job_id: str, state: str) -> None:
        """Отметить итоговое состояние запуска (``ready``/``failed``)."""
        await self.vk.hset(
            f"{_META_PREFIX}{job_id}", mapping={"state": state, "finished_at": time.time()}
        )

    async def append(self, job_id: str, chunk: str) -> None:
        """Добавить кусок сырого вывода + опубликовать для live-подписчиков."""
        key = f"{_LINES_PREFIX}{job_id}"
        await self.vk.rpush(key, chunk)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_EVENTS_PREFIX}{job_id}", chunk)

    async def tail(self, job_id: str) -> list[str]:
        """Весь накопленный сырой вывод job'а (в хронологическом порядке)."""
        return await self.vk.lrange(f"{_LINES_PREFIX}{job_id}", 0, -1)

    async def recent_jobs(self) -> list[dict]:
        """Метаданные последних запусков (для листинга в админке)."""
        ids = await self.vk.lrange(_JOBS_KEY, 0, self.max_jobs - 1)
        out: list[dict] = []
        for job_id in ids:
            meta = await self.vk.hgetall(f"{_META_PREFIX}{job_id}")
            if meta:
                out.append({"job_id": job_id, **meta})
        return out


__all__ = ["ProcLog"]
