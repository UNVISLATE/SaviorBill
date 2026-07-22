"""Heartbeat mediaworker: push CPU%/RSS/current_job в ``media:metrics:{consumer}``.

Формат хэша и семантика — общие с billing/luaworker (см.
``src/telemetry/instance_metrics.py`` на billing-стороне): ``service``,
``consumer``, ``started_at``, ``last_seen_at``, ``cpu_percent``, ``rss_mb``,
плюс media-специфичное ``current_job`` — JSON ``{"token","op","started_at"}``
активной прямо сейчас конвертации, или ``""``, если воркер сейчас свободен.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import valkey.asyncio as valkey

from .config import Config
from .worker import Worker

log = logging.getLogger("saviorbill.media.metrics")


class MetricsPusher:
    """Фоновая задача: раз в ``MEDIA_METRICS_INTERVAL_SEC`` пушить снимок
    собственного потребления процесса + текущей джобы."""

    def __init__(self, cfg: Config, vk: valkey.Valkey, worker: Worker) -> None:
        self.cfg = cfg
        self.vk = vk
        self.worker = worker
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._started_at = time.time()
        self._proc = None

    async def start(self) -> None:
        import psutil

        self._proc = psutil.Process(os.getpid())
        self._proc.cpu_percent()  # baseline-замер (первое значение всегда 0.0)
        self._task = asyncio.create_task(self._run(), name="media-metrics-pusher")

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
                log.exception("media-metrics-pusher: push error")
            await asyncio.sleep(self.cfg.metrics_interval_sec)

    async def _push_once(self) -> None:
        job = self.worker.current_job()
        current_job = json.dumps(job) if job else ""
        key = f"media:metrics:{self.cfg.consumer}"
        await self.vk.hset(
            key,
            mapping={
                "service": "media",
                "consumer": self.cfg.consumer,
                "started_at": self._started_at,
                "last_seen_at": time.time(),
                "cpu_percent": f"{self._proc.cpu_percent():.2f}",
                "rss_mb": f"{self._proc.memory_info().rss / (1024 * 1024):.2f}",
                "current_job": current_job,
            },
        )
        await self.vk.expire(key, self.cfg.metrics_ttl_sec)


__all__ = ["MetricsPusher"]
