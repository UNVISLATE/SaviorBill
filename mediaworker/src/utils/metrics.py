"""Heartbeat mediaworker: push CPU%/RSS/current_job в ``media:metrics:{consumer}``."""

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
        import psutil

        cpu = self._proc.cpu_percent()
        rss = self._proc.memory_info().rss
        subprocesses: list[dict] = []
        try:
            for child in self._proc.children(recursive=True):
                try:
                    child_cpu = child.cpu_percent()
                    child_rss = child.memory_info().rss
                    child_cmd = " ".join(child.cmdline())
                    child_started = child.create_time()
                    subprocesses.append({
                        "pid": child.pid,
                        "name": child.name(),
                        "cmdline": child_cmd,
                        "cpu_percent": round(child_cpu, 1),
                        "rss_mb": round(child_rss / (1024 * 1024), 2),
                        "started_at": child_started,
                        "running_sec": max(0.0, round(time.time() - child_started, 1)),
                    })
                    cpu += child_cpu
                    rss += child_rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        await self.vk.hset(
            key,
            mapping={
                "service": "media",
                "consumer": self.cfg.consumer,
                "started_at": self._started_at,
                "last_seen_at": time.time(),
                "cpu_percent": f"{cpu:.2f}",
                "rss_mb": f"{rss / (1024 * 1024):.2f}",
                "current_job": current_job,
                "subprocesses": json.dumps(subprocesses),
            },
        )
        await self.vk.expire(key, self.cfg.metrics_ttl_sec)


__all__ = ["MetricsPusher"]
