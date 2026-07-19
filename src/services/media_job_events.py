"""Консьюмер переходов статуса медиа-задач (mediaworker → billing).

mediaworker публикует facт перехода состояния (queued/processing/ready/
failed/...) в стрим ``media:job_events`` из того же места, где пишет свой
Valkey ``TaskLog`` (см. ``mediaworker/src/utils/task_log.py``). billing
(владелец схемы БД) потребляет их через consumer-группу и материализует в
``worker_jobs``/``worker_job_events`` (см. ``models/worker_jobs.py``) — так
статус одной джобы и статус в списке всегда читаются из одного источника,
без риска рассинхронизации между разными Valkey-ключами разного TTL.

Устроено по образцу ``services/media_results.py`` (тот же стрим-протокол,
та же consumer-группа-на-сервис).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import AppConfig
from models.worker_jobs import WorkerJobsMngr
from security.sec.bus_sign import verify_fields
from telemetry.metrics import (
    bus_signature_rejected_total,
    worker_jobs_failed_total,
    worker_jobs_pending,
    worker_jobs_reclaimed_total,
)
from telemetry.otel import span_from_carrier

log = logging.getLogger("saviorbill.media")

# Как часто проверять "зависшие" processing-джобы (см. sweep_stale) — не на
# каждой итерации цикла, иначе лишний DB round-trip на пустом чтении стрима.
_SWEEP_INTERVAL_SEC = 60


class MediaJobEvents:
    """Фоновый консьюмер стрима переходов статуса медиа-задач."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        vk: valkey.Valkey,
        cfg: AppConfig,
    ) -> None:
        self.sm = sessionmaker
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._last_sweep = 0.0

    async def _ensure_group(self) -> None:
        try:
            await self.vk.xgroup_create(
                self.cfg.MEDIA_JOB_EVENTS_STREAM,
                self.cfg.MEDIA_JOB_EVENTS_GROUP,
                id="0",
                mkstream=True,
            )
        except valkey.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def start(self) -> None:
        await self._ensure_group()
        self._task = asyncio.create_task(self._run(), name="media-job-events")
        log.info("media-job-events the consumer is launched")

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
        consumer = self.cfg.instance_id
        while not self._stopped:
            try:
                resp = await self.vk.xreadgroup(
                    self.cfg.MEDIA_JOB_EVENTS_GROUP,
                    consumer,
                    {self.cfg.MEDIA_JOB_EVENTS_STREAM: ">"},
                    count=20,
                    block=5000,
                )
            except asyncio.CancelledError:
                raise
            except (valkey.TimeoutError, asyncio.TimeoutError):
                await self._maybe_sweep()
                continue
            except Exception:  # noqa: BLE001 — цикл не должен падать
                log.exception("media-job-events: reading error")
                await asyncio.sleep(2)
                continue
            for _stream, entries in resp or []:
                for msg_id, data in entries:
                    try:
                        if not verify_fields(self.cfg.BUS_SIGNING_KEY, data):
                            bus_signature_rejected_total.labels(bus="media_job_events").inc()
                            log.warning(
                                "media-job-events: сообщение %s отклонено — "
                                "неверная подпись",
                                msg_id,
                            )
                            continue
                        with span_from_carrier("media.job_event.consume", data):
                            await self._handle(data)
                    except Exception:  # noqa: BLE001 — одна запись не валит цикл
                        log.exception("media-job-events: recording error")
                    finally:
                        await self.vk.xack(
                            self.cfg.MEDIA_JOB_EVENTS_STREAM,
                            self.cfg.MEDIA_JOB_EVENTS_GROUP,
                            msg_id,
                        )
            await self._maybe_sweep()

    async def _maybe_sweep(self) -> None:
        """Периодически помечать `stale` джобы, зависшие в processing.

        Отдельный механизм от Stream-level reclaim воркера (§3.1 плана) —
        покрывает случай, когда воркер упал уже после xack/до финального
        события и billing никогда не получит ready/failed для этой джобы.
        """
        now = time.monotonic()
        if now - self._last_sweep < _SWEEP_INTERVAL_SEC:
            return
        self._last_sweep = now
        try:
            async with self.sm() as session:
                mngr = WorkerJobsMngr(session)
                n = await mngr.sweep_stale(
                    timedelta(seconds=self.cfg.MEDIA_JOB_STALE_AFTER_SEC)
                )
                await session.commit()
                worker_jobs_pending.labels(kind="media").set(
                    await mngr.count_pending("media")
                )
            if n:
                log.warning("media-job-events: %s job(s) marked stale", n)
                worker_jobs_reclaimed_total.labels(kind="media").inc(n)
        except Exception:  # noqa: BLE001 — sweep не должен ронять консьюмер
            log.exception("media-job-events: sweep_stale error")

    async def _handle(self, data: dict) -> None:
        op = data.get("op", "")
        token = data.get("token", "")
        state = data.get("state", "")
        detail = data.get("detail") or None
        if not (op and token and state):
            return
        async with self.sm() as session:
            mngr = WorkerJobsMngr(session)
            await mngr.apply(
                kind="media",
                op=op,
                subject_key=token,
                state=state,
                error=detail if state in ("failed", "stale") else None,
            )
            await session.commit()
        if state == "failed":
            worker_jobs_failed_total.labels(kind="media", op=op).inc()


__all__ = ["MediaJobEvents"]
