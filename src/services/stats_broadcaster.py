"""Общий фоновый поллер снапшота инстансов для WS `/api/ws/v1/system/stats`.

Раньше каждый WS-клиент сам дёргал ``list_instances`` (SCAN+HGETALL в Valkey)
на собственном таймере (1..60с, по выбору клиента) — много подключений с
маленьким интервалом ощутимо грузили Valkey (см. AUDIT.md §3.5). Здесь один
процесс держит один фоновый таймер с фиксированным (минимально допустимым)
периодом и кэширует последний снапшот в памяти; WS-роут отдаёт клиентам этот
кэш на их собственном (по-прежнему настраиваемом в допустимых пределах)
таймере, не порождая для этого новых запросов к Valkey.
"""

from __future__ import annotations

import asyncio
import logging

import valkey.asyncio as valkey

from core.config import AppConfig
from telemetry.instance_metrics import list_instances

log = logging.getLogger("saviorbill.system_stats")


class StatsBroadcaster:
    """Единственный источник снапшота инстансов для всех WS-подписчиков."""

    def __init__(self, vk: valkey.Valkey, cfg: AppConfig) -> None:
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._stopped = False
        self.snapshot: dict = {"instances": [], "aggregate": {}}
        # Отдельное поле (не читаем cfg внутри цикла) — удобно переопределить
        # в тестах без мока всего AppConfig.
        self._interval = max(1, cfg.SYSTEM_STATS_WS_MIN_SEC)

    async def start(self) -> None:
        # Первый снапшот — сразу, чтобы первый подключившийся клиент не ждал
        # целый период поллинга.
        try:
            self.snapshot = await list_instances(self.vk)
        except Exception:  # noqa: BLE001
            log.warning("initial system-stats snapshot failed", exc_info=True)
        self._task = asyncio.create_task(self._run(), name="system-stats-broadcaster")

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._interval)
            try:
                self.snapshot = await list_instances(self.vk)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.warning("system-stats poll failed", exc_info=True)


__all__ = ["StatsBroadcaster"]
