"""Периодический сбор метрик LuaWorker из Valkey и переэкспорт в Prometheus.

LuaWorker сам не поднимает HTTP (`/metrics`) — вместо pull он push'ит снимок
своих счётчиков в Valkey-хэш ``lua:metrics:{consumer}`` (см.
``luaworker/src/main.lua::maybe_push_metrics``) раз в ``LUA_METRICS_INTERVAL_SEC``.
Этот модуль читает эти хэши через ``SCAN`` (не блокирует Valkey, в отличие от
``KEYS``) и переносит значения в Prometheus Gauge с лейблом ``consumer`` — так
все реплики воркера видны в Grafana по отдельности.

Значения счётчиков — накопительные с момента старта процесса воркера (не
Prometheus-Counter, т.к. могут обнулиться при рестарте воркера без явного
сигнала об этом billing-стороне) — обнуление видно на графике как обрыв, это
ожидаемо, не баг сборщика.
"""

from __future__ import annotations

import asyncio
import logging

import valkey.asyncio as valkey
from prometheus_client import Gauge

from core.config import AppConfig

log = logging.getLogger("saviorbill.lua_metrics")

lua_worker_processed_total = Gauge(
    "lua_worker_processed_total", "Задач, обработанных репликой LuaWorker", ["consumer"]
)
lua_worker_errors_total = Gauge(
    "lua_worker_errors_total", "Задач, завершившихся ошибкой", ["consumer"]
)
lua_worker_reclaimed_total = Gauge(
    "lua_worker_reclaimed_total", "Задач, забранных через XCLAIM у упавшего консьюмера", ["consumer"]
)
lua_worker_avg_exec_ms = Gauge(
    "lua_worker_avg_exec_ms", "Среднее время исполнения задачи, мс", ["consumer"]
)
lua_worker_last_seen_seconds = Gauge(
    "lua_worker_last_seen_seconds",
    "Unix-время последнего пуша метрик репликой (для расчёта staleness в PromQL)",
    ["consumer"],
)


class LuaMetricsCollector:
    """Фоновая задача: раз в ``LUA_METRICS_POLL_INTERVAL_SEC`` синхронизировать
    Prometheus Gauge'и с ``lua:metrics:*`` в Valkey."""

    def __init__(self, vk: valkey.Valkey, cfg: AppConfig) -> None:
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._known_consumers: set[str] = set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="lua-metrics-collector")

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
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — сбор метрик не должен ронять процесс
                log.exception("lua-metrics-collector: poll error")
            await asyncio.sleep(self.cfg.LUA_METRICS_POLL_INTERVAL_SEC)

    async def _poll_once(self) -> None:
        prefix = self.cfg.LUA_METRICS_PREFIX
        seen: set[str] = set()
        cursor = 0
        while True:
            cursor, keys = await self.vk.scan(cursor, match=f"{prefix}*", count=100)
            for key in keys:
                consumer = key[len(prefix) :]
                seen.add(consumer)
                data = await self.vk.hgetall(key)
                self._apply(consumer, data)
            if cursor == 0:
                break
        # Реплика, чей ключ протух (TTL истёк — процесс не пушил метрики
        # LUA_METRICS_TTL_SEC) — убрать её из Gauge, а не оставлять последнее
        # известное значение навечно.
        for stale in self._known_consumers - seen:
            for gauge in (
                lua_worker_processed_total,
                lua_worker_errors_total,
                lua_worker_reclaimed_total,
                lua_worker_avg_exec_ms,
                lua_worker_last_seen_seconds,
            ):
                gauge.remove(stale)
        self._known_consumers = seen

    @staticmethod
    def _apply(consumer: str, data: dict) -> None:
        def _num(key: str) -> float:
            try:
                return float(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        lua_worker_processed_total.labels(consumer=consumer).set(_num("processed_total"))
        lua_worker_errors_total.labels(consumer=consumer).set(_num("errors_total"))
        lua_worker_reclaimed_total.labels(consumer=consumer).set(_num("reclaimed_total"))
        lua_worker_avg_exec_ms.labels(consumer=consumer).set(_num("avg_exec_ms"))
        lua_worker_last_seen_seconds.labels(consumer=consumer).set(_num("last_seen_at"))


__all__ = ["LuaMetricsCollector"]
