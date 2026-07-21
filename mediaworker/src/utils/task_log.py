"""Журнал фактов о медиа-тасках (mediaworker) — независим от OTEL.

Хранится в Valkey кольцевым буфером (``LPUSH``+``LTRIM``+``EXPIRE``) под
ключом ``tasklog:media``. Одновременно каждая запись публикуется в Pub/Sub
канал ``tasklog:events:media`` для realtime-хвоста через WS

Формат записи общий с billing-стороной (``src/utils/task_log.py`` в
billing) — оба сервиса пишут в тот же Valkey тем же контрактом, но никогда
не импортируют код друг друга (сервисы не делят код, см. прецедент
``telemetry.py``).
"""

from __future__ import annotations

import json
import time

import valkey.asyncio as valkey

from .bus_sign import sign_fields
from .telemetry import current_trace_id

_PREFIX = "tasklog:"
_EVENTS_PREFIX = "tasklog:events:"


class TaskLog:
    """Журнал фактов о тасках одного вида (``kind``, напр. ``"media"``)."""

    def __init__(
        self,
        vk: valkey.Valkey,
        max_len: int = 500,
        ttl: int = 604_800,
        *,
        job_events_stream: str | None = None,
        job_events_maxlen: int = 10_000,
        signing_key: str = "",
    ) -> None:
        self.vk = vk
        self.max_len = max_len
        self.ttl = ttl
        # Публикация в стрим для billing (state machine `worker_jobs`, см.
        # billing `models/worker_jobs.py`) — только для kind == "media"
        # (единственный протяжённый во времени, межпроцессный жизненный цикл,
        # см. докстринг там же). `None`/пустая строка отключает публикацию —
        # так работают тесты и любые сборки, где billing-consumer не поднят.
        self.job_events_stream = job_events_stream or None
        self.job_events_maxlen = job_events_maxlen
        self.signing_key = signing_key

    async def record(
        self,
        *,
        kind: str,
        op: str,
        token_or_cid: str,
        state: str,
        detail: str | None = None,
        owner_id: str | None = None,
    ) -> None:
        """Добавить факт в кольцевой буфер + опубликовать событие для WS."""
        entry = {
            "ts": time.time(),
            "kind": kind,
            "op": op,
            "token_or_cid": token_or_cid,
            "state": state,
            "detail": detail,
            # None, если OTEL выключен (OTEL_ENABLED=false) — журнал работает
            # независимо от трейсинга, trace_id тут чисто для сшивки при
            # необходимости.
            "trace_id": current_trace_id(),
        }
        raw = json.dumps(entry, ensure_ascii=False)
        key = f"{_PREFIX}{kind}"
        await self.vk.lpush(key, raw)
        await self.vk.ltrim(key, 0, self.max_len - 1)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_EVENTS_PREFIX}{kind}", raw)
        if kind == "media" and self.job_events_stream:
            await self.vk.xadd(
                self.job_events_stream,
                sign_fields(
                    self.signing_key,
                    {
                        "op": op,
                        "token": token_or_cid,
                        "state": state,
                        "detail": detail or "",
                        # Владелец — только у ``convert`` известен сразу (из
                        # исходной задачи в очереди, см. upload.py), у
                        # preview_add/thumb_replace тоже передаётся явно (см.
                        # serve.py — известен из _authorize_media_owner).
                        # billing денормализует его в саму джобу (см.
                        # models/worker_jobs.py::apply) — без ожидания
                        # появления system_media (создаётся только по
                        # результату конвертации).
                        "owner_id": owner_id or "",
                    },
                ),
                maxlen=self.job_events_maxlen,
                approximate=True,
            )

    async def tail(self, kind: str, limit: int = 100) -> list[dict]:
        """Последние ``limit`` фактов (от новых к старым)."""
        raw = await self.vk.lrange(f"{_PREFIX}{kind}", 0, limit - 1)
        out: list[dict] = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except (TypeError, ValueError):
                continue
        return out


__all__ = ["TaskLog"]
