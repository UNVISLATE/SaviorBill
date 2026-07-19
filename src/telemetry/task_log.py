"""Журнал фактов о фоновых тасках (lua/media) — независим от OTEL.

Хранится в Valkey кольцевым буфером (``LPUSH``+``LTRIM``+``EXPIRE``) на
каждый вид тасков (``kind``: ``"lua"`` | ``"media"``). Одновременно каждая
запись публикуется в Pub/Sub канал ``tasklog:events:{kind}`` — на него
подписывается WS-роутер realtime-хвоста (``apiws/v1/tasks.py``).

Формат общий с mediaworker-стороной (``mediaworker/src/utils/task_log.py``)
— оба сервиса пишут в один и тот же Valkey одним контрактом полей, но
никогда не импортируют код друг друга (сервисы не делят код, см. прецедент
``telemetry.py``).

Почему не Postgres: это оперативные факты для отладки/мониторинга, не
бизнес-данные — хранить в БД означало бы лишнюю миграцию и нагрузку на
запись при каждом таске. Почему не бесконечный стрим: ``LTRIM`` даёт
предсказуемый размер без отдельного cron/cleanup-джоба
"""

from __future__ import annotations

import json
import time

import valkey.asyncio as valkey

from telemetry.otel import current_trace_id

_PREFIX = "tasklog:"
_EVENTS_PREFIX = "tasklog:events:"


class TaskLog:
    """Журнал фактов о тасках одного вида (``kind``: ``"lua"``/``"media"``)."""

    def __init__(
        self, vk: valkey.Valkey, max_len: int = 500, ttl: int = 604_800
    ) -> None:
        self.vk = vk
        self.max_len = max_len
        self.ttl = ttl

    async def record(
        self,
        *,
        kind: str,
        op: str,
        token_or_cid: str,
        state: str,
        detail: str | None = None,
    ) -> None:
        """Добавить факт в кольцевой буфер + опубликовать событие для WS."""
        entry = {
            "ts": time.time(),
            "kind": kind,
            "op": op,
            "token_or_cid": token_or_cid,
            "state": state,
            "detail": detail,
            # None, если OTEL выключен — журнал работает независимо от
            # трейсинга, trace_id только для сшивки при необходимости.
            "trace_id": current_trace_id(),
        }
        raw = json.dumps(entry, ensure_ascii=False)
        key = f"{_PREFIX}{kind}"
        await self.vk.lpush(key, raw)
        await self.vk.ltrim(key, 0, self.max_len - 1)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_EVENTS_PREFIX}{kind}", raw)

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
