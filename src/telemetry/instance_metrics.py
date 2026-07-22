"""Мониторинг живых инстансов (billing/media/lua): heartbeat + CPU/RSS.

Каждый инстанс (billing сам себе, mediaworker, luaworker) периодически
push'ит снимок своего состояния в Valkey-хэш ``{service}:metrics:{consumer}``
(TTL чуть больше периода пуша — умерший процесс просто не продлит TTL, и хэш
пропадает сам). Общий формат полей:

```
service        "lua"|"media"|"billing"
consumer       "<hostname>-<pid|random>"
started_at     unix ts запуска процесса (для uptime)
last_seen_at   unix ts последнего пуша
cpu_percent    float — своё потребление CPU процесса (не всего сервера)
rss_mb         float — своя резидентная память процесса, МиБ
# lua-специфично:
processed_total, errors_total, reclaimed_total, avg_exec_ms
# media-специфично:
current_job    JSON {"token","op","started_at"} или "" — что сейчас в работе
```

Этот модуль — read-side (``list_instances``/``get_instance``, используются
``api/v1/system/stats.py``) и Prometheus-переэкспорт lua-счётчиков
(``LuaMetricsCollector`` — было в ``telemetry/lua_metrics.py``, перенесено
сюда при обобщении на все 3 сервиса, см. IMPLEMENTATION_PLAN.md §1). Push
собственных метрик billing — ``SelfMetricsPusher`` ниже; mediaworker и
luaworker пушат сами себе (см. ``mediaworker/src/utils/metrics.py`` и
``luaworker/src/main.lua::maybe_push_metrics``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import valkey.asyncio as valkey
from prometheus_client import Gauge

from core.config import AppConfig

log = logging.getLogger("saviorbill.instance_metrics")

SERVICES = ("lua", "media", "billing")

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


def _metrics_key(service: str, consumer: str) -> str:
    return f"{service}:metrics:{consumer}"


def _num(data: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(data.get(key, default) or default)
    except (TypeError, ValueError):
        return default


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
        lua_worker_processed_total.labels(consumer=consumer).set(_num(data, "processed_total"))
        lua_worker_errors_total.labels(consumer=consumer).set(_num(data, "errors_total"))
        lua_worker_reclaimed_total.labels(consumer=consumer).set(_num(data, "reclaimed_total"))
        lua_worker_avg_exec_ms.labels(consumer=consumer).set(_num(data, "avg_exec_ms"))
        lua_worker_last_seen_seconds.labels(consumer=consumer).set(_num(data, "last_seen_at"))


class SelfMetricsPusher:
    """Периодический пуш собственных CPU/RSS billing-процесса в
    ``billing:metrics:{consumer}`` — billing виден в списке инстансов наравне
    с media/lua (см. §1: "billing тоже шлёт heartbeat сам себе")."""

    def __init__(self, vk: valkey.Valkey, cfg: AppConfig) -> None:
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._started_at = time.time()
        self._proc = None

    async def start(self) -> None:
        # psutil.Process() — ленивая инициализация здесь, а не на уровне
        # модуля: конструктор дёргает первый cpu_percent()-замер (baseline),
        # который должен стартовать вместе с самим пушером, а не при импорте.
        import psutil

        self._proc = psutil.Process(os.getpid())
        self._proc.cpu_percent()  # baseline-замер, первое значение всегда 0.0
        self._task = asyncio.create_task(self._run(), name="self-metrics-pusher")

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
                await self._push_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — heartbeat не должен ронять процесс
                log.exception("self-metrics-pusher: push error")
            await asyncio.sleep(self.cfg.SELF_METRICS_INTERVAL_SEC)

    async def _push_once(self) -> None:
        rss_mb = self._proc.memory_info().rss / (1024 * 1024)
        cpu_percent = self._proc.cpu_percent()
        key = _metrics_key("billing", self.cfg.instance_id)
        await self.vk.hset(
            key,
            mapping={
                "service": "billing",
                "consumer": self.cfg.instance_id,
                "started_at": self._started_at,
                "last_seen_at": time.time(),
                "cpu_percent": f"{cpu_percent:.2f}",
                "rss_mb": f"{rss_mb:.2f}",
            },
        )
        await self.vk.expire(key, self.cfg.SELF_METRICS_TTL_SEC)


async def list_instances(vk: valkey.Valkey) -> dict:
    """Список всех живых инстансов + агрегаты по типу сервиса и общий итог.

    "online" здесь тождественно "ключ существует" — Valkey сам убирает
    протухшие по TTL хэши, отдельно проверять staleness не нужно.
    """
    instances: list[dict] = []
    totals_by_service: dict[str, dict] = {
        svc: {"count": 0, "cpu_percent": 0.0, "rss_mb": 0.0} for svc in SERVICES
    }
    for svc in SERVICES:
        prefix = f"{svc}:metrics:"
        cursor = 0
        while True:
            cursor, keys = await vk.scan(cursor, match=f"{prefix}*", count=100)
            for key in keys:
                consumer = key[len(prefix) :]
                data = await vk.hgetall(key)
                if not data:
                    continue
                cpu = _num(data, "cpu_percent")
                rss = _num(data, "rss_mb")
                instances.append(
                    {
                        "service": svc,
                        "consumer": consumer,
                        "online": True,
                        "uptime_sec": max(0.0, time.time() - _num(data, "started_at")),
                        "cpu_percent": cpu,
                        "rss_mb": rss,
                        "last_seen_at": _num(data, "last_seen_at"),
                    }
                )
                totals_by_service[svc]["count"] += 1
                totals_by_service[svc]["cpu_percent"] += cpu
                totals_by_service[svc]["rss_mb"] += rss
            if cursor == 0:
                break
    grand_total = {
        "count": sum(t["count"] for t in totals_by_service.values()),
        "cpu_percent": sum(t["cpu_percent"] for t in totals_by_service.values()),
        "rss_mb": sum(t["rss_mb"] for t in totals_by_service.values()),
    }
    instances.sort(key=lambda i: (i["service"], i["consumer"]))
    return {
        "instances": instances,
        "totals_by_service": totals_by_service,
        "grand_total": grand_total,
    }


async def get_instance(vk: valkey.Valkey, service: str, consumer: str) -> dict | None:
    """Полная запись хэша одного инстанса; для media + активной джобы —
    подтянуть ``media:status:{token}`` (см. §1.3: не только "что", но и
    "на каком проценте")."""
    if service not in SERVICES:
        return None
    data = await vk.hgetall(_metrics_key(service, consumer))
    if not data:
        return None
    out = {
        "service": service,
        "consumer": consumer,
        "online": True,
        "uptime_sec": max(0.0, time.time() - _num(data, "started_at")),
        "last_seen_at": _num(data, "last_seen_at"),
        "cpu_percent": _num(data, "cpu_percent"),
        "rss_mb": _num(data, "rss_mb"),
        "raw": data,
    }
    current_job_token = None
    if service == "media" and data.get("current_job"):
        try:
            job = json.loads(data["current_job"])
            out["current_job"] = job
            current_job_token = job.get("token")
        except (ValueError, TypeError):
            out["current_job"] = None
    if current_job_token:
        status = await vk.hgetall(f"media:status:{current_job_token}")
        if status:
            out["current_job_status"] = {
                "state": status.get("state"),
                "percent": _num(status, "percent") if status.get("percent") else None,
                "eta_sec": _num(status, "eta_sec") if status.get("eta_sec") else None,
            }
    return out


__all__ = [
    "SERVICES",
    "LuaMetricsCollector",
    "SelfMetricsPusher",
    "list_instances",
    "get_instance",
]
