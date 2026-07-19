"""Журнал сырого вывода ffmpeg/ffprobe (mediaworker) для realtime-логов в UI.

Отдельно от ``task_log.py`` (структурированные факты о статусах тасков):
здесь хранится именно **сырой текст**, который печатает сам процесс
(включая прогресс-строки с ``\\r`` без ``\\n``) — чтобы админ мог смотреть
за ним в реальном времени через xterm.js, как за обычным терминалом.

Схема хранения в Valkey

- ``proclog:jobs`` — список последних ``max_jobs`` job_id (кольцевой буфер,
  ``LPUSH``+``LTRIM``) — для листинга "какие запуски были недавно".
- ``proclog:meta:{job_id}`` — hash с метаданными запуска (``op``, ``token``,
  ``state``, ``stage``, ``started_at``, ``finished_at``), TTL = ``ttl``.
  ``stage`` — текущий под-этап многошагового job'а (см. ``set_stage()``):
  для видео-конвертации это ``encode`` → ``thumb`` → ``preview`` →
  ``publish`` → финальный ``ready``/``failed``; для одношаговых job'ов
  (``preview_add``/``thumb_replace``) совпадает с ``op`` до самого конца.
- ``proclog:lines:{job_id}`` — список кусков сырого вывода в хронологическом
  порядке (``RPUSH``), TTL = ``ttl`` — для отдачи бэклога при подключении.
- ``proclog:events:{job_id}`` — Pub/Sub канал, каждый кусок публикуется как
  есть (plain text) для live-форвардинга через WS.
- ``proclog:progress:{job_id}`` — hash со структурированным снимком прогресса
  (``percent``/``eta_sec``/``fps``/``speed``/``frame``/``out_time_sec``),
  TTL = ``ttl`` — отдельно от сырого лога (см. ``utils/ffprogress.py``: это
  разобранный machine-readable вывод ffmpeg, не текст терминала).
- ``proclog:progress-events:{job_id}`` — Pub/Sub канал, каждый снимок
  публикуется как JSON для live-форвардинга через отдельный WS-эндпоинт.
- ``proclog:token_jobs:{token}`` — список job_id, относящихся к одному
  media-токену (``RPUSH``), TTL = ``ttl`` — по нему ``/api/media/status/{token}``
  собирает сводку активных/недавних job'ов без сканирования всех job'ов.

Один job_id — один запуск ffmpeg/ffprobe (не один token медиа): для одного
token может параллельно идти и конвертация, и генерация доп. превью — у
каждой свой job_id и свой независимый лог.
"""

from __future__ import annotations

import json
import time
import uuid

import valkey.asyncio as valkey

_JOBS_KEY = "proclog:jobs"
_META_PREFIX = "proclog:meta:"
_LINES_PREFIX = "proclog:lines:"
_EVENTS_PREFIX = "proclog:events:"
_PROGRESS_PREFIX = "proclog:progress:"
_PROGRESS_EVENTS_PREFIX = "proclog:progress-events:"
_TOKEN_JOBS_PREFIX = "proclog:token_jobs:"


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
            mapping={
                "op": op,
                "token": token,
                "state": "running",
                "stage": op,
                "started_at": time.time(),
            },
        )
        await self.vk.expire(meta_key, self.ttl)
        await self.vk.lpush(_JOBS_KEY, job_id)
        await self.vk.ltrim(_JOBS_KEY, 0, self.max_jobs - 1)
        token_key = f"{_TOKEN_JOBS_PREFIX}{token}"
        await self.vk.rpush(token_key, job_id)
        await self.vk.expire(token_key, self.ttl)
        return job_id

    async def set_stage(self, job_id: str, stage: str) -> None:
        """Обновить текущий под-этап многошагового job'а (например, для
        ``convert`` видео: ``encode`` → ``thumb`` → ``preview`` → ``publish``).

        Без этого поля клиент видел один "running" job без объяснения, чем
        конкретно он сейчас занят между окончанием прогресса кодирования
        (percent/eta доходят до 100%) и итоговым ``finish_job`` — генерация
        thumb/preview/загрузка вариантов в хранилище проходила "невидимо".
        """
        await self.vk.hset(f"{_META_PREFIX}{job_id}", mapping={"stage": stage})

    async def finish_job(self, job_id: str, state: str) -> None:
        """Отметить итоговое состояние запуска (``ready``/``failed``)."""
        await self.vk.hset(
            f"{_META_PREFIX}{job_id}",
            mapping={"state": state, "stage": state, "finished_at": time.time()},
        )

    def events_channel(self, job_id: str) -> str:
        """Pub/Sub-канал сырого вывода job'а (для WS-форвардинга)."""
        return f"{_EVENTS_PREFIX}{job_id}"

    def progress_channel(self, job_id: str) -> str:
        """Pub/Sub-канал JSON-снимков прогресса job'а (для WS-форвардинга)."""
        return f"{_PROGRESS_EVENTS_PREFIX}{job_id}"

    async def append(self, job_id: str, chunk: str) -> None:
        """Добавить кусок сырого вывода + опубликовать для live-подписчиков."""
        key = f"{_LINES_PREFIX}{job_id}"
        await self.vk.rpush(key, chunk)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_EVENTS_PREFIX}{job_id}", chunk)

    async def set_progress(self, job_id: str, **fields: object) -> None:
        """Обновить снимок прогресса (percent/eta_sec/fps/...) + уведомить
        live-подписчиков. Отдельно от ``append()`` — здесь структурированный
        JSON-снимок (см. ``utils/ffprogress.py``), а не сырой текст терминала.
        """
        key = f"{_PROGRESS_PREFIX}{job_id}"
        # Valkey hash принимает только bytes/str/int/float — bool (``done``)
        # нужно привести явно, иначе клиент кидает DataError на каждый снимок
        # (наблюдалось как зависшая конвертация: исключение из on_progress
        # рушило весь _convert(), и задача ретраилась бесконечно).
        payload = {k: ("" if v is None else int(v) if isinstance(v, bool) else v) for k, v in fields.items()}
        await self.vk.hset(key, mapping=payload)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_PROGRESS_EVENTS_PREFIX}{job_id}", json.dumps(fields, default=str))

    async def tail(self, job_id: str) -> list[str]:
        """Весь накопленный сырой вывод job'а (в хронологическом порядке)."""
        return await self.vk.lrange(f"{_LINES_PREFIX}{job_id}", 0, -1)

    async def get_progress(self, job_id: str) -> dict:
        """Последний известный снимок прогресса job'а (или ``{}``, если нет)."""
        return await self.vk.hgetall(f"{_PROGRESS_PREFIX}{job_id}")

    async def get_job(self, job_id: str) -> dict | None:
        """Метаданные одного запуска (или ``None``, если TTL истёк/не найден)."""
        meta = await self.vk.hgetall(f"{_META_PREFIX}{job_id}")
        if not meta:
            return None
        return {"job_id": job_id, **meta}

    async def recent_jobs(self, limit: int | None = None) -> list[dict]:
        """Метаданные последних запусков (для листинга в админке)."""
        cap = self.max_jobs if limit is None else min(limit, self.max_jobs)
        ids = await self.vk.lrange(_JOBS_KEY, 0, cap - 1)
        out: list[dict] = []
        for job_id in ids:
            meta = await self.vk.hgetall(f"{_META_PREFIX}{job_id}")
            if meta:
                out.append({"job_id": job_id, **meta})
        return out

    async def jobs_for_token(self, token: str) -> list[dict]:
        """Job'ы (с прогрессом, если есть) одного media-токена — для
        ``GET /api/media/status/{token}``: сводка "что сейчас происходит с
        файлом", а не просто финальный ``ready``/``failed``.
        """
        ids = await self.vk.lrange(f"{_TOKEN_JOBS_PREFIX}{token}", 0, -1)
        out: list[dict] = []
        for job_id in ids:
            meta = await self.vk.hgetall(f"{_META_PREFIX}{job_id}")
            if not meta:
                continue
            progress = await self.vk.hgetall(f"{_PROGRESS_PREFIX}{job_id}")
            entry = {
                "job_id": job_id,
                "op": meta.get("op"),
                "status": meta.get("state"),
                "stage": meta.get("stage"),
                "percent": progress.get("percent") or None,
                "eta_sec": progress.get("eta_sec") or None,
            }
            out.append(entry)
        return out


__all__ = ["ProcLog"]
