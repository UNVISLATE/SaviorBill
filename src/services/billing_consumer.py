"""Консьюмер готовых задач от Go-планировщика ``scheduler`` (Valkey Stream)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

import valkey.asyncio as valkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import AppConfig
from models.scheduled_tasks import ScheduledTaskModel
from security.sec.bus_sign import verify_fields
from services.audit import audit
from services.billing_executor import BillingExecutor
from telemetry.metrics import bus_signature_rejected_total
from telemetry.task_log import TaskLog
from utils.datetime_utils import utc_now

log = logging.getLogger("saviorbill.billing.consumer")

_RETRY_BASE_SEC = 15


def _s(v: object) -> str:
    return v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)


class BillingTaskConsumer:
    """Читает ``BILLING_READY_STREAM`` через Consumer Group и исполняет задачи."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        vk: valkey.Valkey,
        cfg: AppConfig,
        task_log: TaskLog | None = None,
    ) -> None:
        self.sm = sessionmaker
        self.vk = vk
        self.cfg = cfg
        self.executor = BillingExecutor(vk, cfg, task_log=task_log)
        self._sem = asyncio.Semaphore(max(1, cfg.BILLING_CONCURRENCY))
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def _ensure_group(self) -> None:
        try:
            await self.vk.xgroup_create(
                self.cfg.BILLING_READY_STREAM,
                self.cfg.BILLING_READY_GROUP,
                id="0",
                mkstream=True,
            )
        except valkey.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def start(self) -> None:
        if not self.cfg.BILLING_EXECUTOR_ENABLED:
            log.info("billing-consumer is disabled (BILLING_EXECUTOR_ENABLED=false)")
            return
        await self._ensure_group()
        self._task = asyncio.create_task(self._run(), name="billing-task-consumer")
        log.info("billing-consumer launched (stream=%s)", self.cfg.BILLING_READY_STREAM)

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
                    self.cfg.BILLING_READY_GROUP,
                    consumer,
                    {self.cfg.BILLING_READY_STREAM: ">"},
                    count=max(1, self.cfg.BILLING_CONCURRENCY),
                    block=5000,
                )
            except asyncio.CancelledError:
                raise
            except (valkey.TimeoutError, asyncio.TimeoutError):
                continue
            except Exception as exc:  # noqa: BLE001
                log.exception("billing-consumer: read error")
                if "NOGROUP" in str(exc):
                    await self._ensure_group()
                await asyncio.sleep(2)
                continue

            coros = []
            for _stream, entries in resp or []:
                for msg_id, raw_data in entries:
                    coros.append(self._process_entry(msg_id, raw_data))
            if coros:
                await asyncio.gather(*coros)

    async def _process_entry(self, msg_id: object, raw_data: dict) -> None:
        data = {_s(k): _s(v) for k, v in raw_data.items()}
        async with self._sem:
            try:
                if not verify_fields(self.cfg.BUS_SIGNING_KEY, data):
                    bus_signature_rejected_total.labels(bus="billing_ready").inc()
                    log.warning("billing-consumer: message %s rejected (bad sig)", msg_id)
                    return
                await self.handle_message(data)
            except Exception:  # noqa: BLE001
                log.exception("billing-consumer: unhandled error for msg=%s", msg_id)
            finally:
                try:
                    await self.vk.xack(
                        self.cfg.BILLING_READY_STREAM,
                        self.cfg.BILLING_READY_GROUP,
                        msg_id,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("billing-consumer: xack failed for msg=%s", msg_id)

    async def handle_message(self, data: dict[str, str]) -> None:
        task_kind = data.get("task_kind", "")
        task_id_raw = data.get("task_id")

        # Периодические cron-события без строки в scheduled_tasks.
        if not task_id_raw:
            await self._handle_cron(task_kind)
            return

        try:
            task_id = int(task_id_raw)
            msg_version = int(data.get("version") or 1)
        except ValueError:
            log.warning("billing-consumer: invalid task_id/version in %r", data)
            return

        media_deletes: list[tuple[str, list[str]]] = []
        try:
            async with self.sm() as session:
                task = await session.scalar(
                    select(ScheduledTaskModel)
                    .where(ScheduledTaskModel.id == task_id)
                    .with_for_update(skip_locked=True)
                )
                if task is None:
                    return
                if task.status not in ("dispatched", "pending"):
                    return
                if task.version != msg_version:
                    # Устаревший таймер — актуальная задача уже перепланирована/отменена.
                    return

                task.status = "processing"
                task.updated_at = utc_now()
                await session.flush()

                media_deletes = await self._dispatch_kind(
                    session, task.task_kind, task.ref_id
                )

                # Хендлеры (exec_pay_recheck / exec_delivery_retry / exec_svc_expire)
                # могут перепланировать задачу через Core upsert (в обход identity map).
                await session.refresh(task)
                if task.status == "processing":
                    task.status = "done"
                    task.locked_until = None
                    task.last_error = None
                    task.updated_at = utc_now()

                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("billing-consumer: task %s (%s) failed", task_id, task_kind)
            await self._handle_failure(task_id, exc)
            return

        if media_deletes:
            bus = self.executor.media_bus()
            for backend, keys in media_deletes:
                await bus.enqueue_delete(backend, keys)

    async def _handle_cron(self, task_kind: str) -> None:
        media_deletes: list[tuple[str, list[str]]] = []
        async with self.sm() as session:
            if task_kind == "cron_media_cleanup":
                media_deletes = await self.executor.exec_cron_media_cleanup(session)
            elif task_kind == "cron_media_sweep":
                await self.executor.exec_cron_media_sweep_stale(session)
            await session.commit()
        if media_deletes:
            bus = self.executor.media_bus()
            for backend, keys in media_deletes:
                await bus.enqueue_delete(backend, keys)

    async def _dispatch_kind(
        self, session: AsyncSession, task_kind: str, ref_id: int | None
    ) -> list[tuple[str, list[str]]]:
        if task_kind == "svc_expire" and ref_id is not None:
            await self.executor.exec_svc_expire(session, ref_id)
            return []
        if task_kind == "svc_provision_poll" and ref_id is not None:
            await self.executor.exec_svc_provision_poll(session, ref_id)
            return []
        if task_kind == "pay_recheck" and ref_id is not None:
            await self.executor.exec_pay_recheck(session, ref_id)
            return []
        if task_kind == "dlv_retry" and ref_id is not None:
            await self.executor.exec_delivery_retry(session, ref_id)
            return []
        if task_kind == "med_expire" and ref_id is not None:
            return await self.executor.exec_media_expire(session, ref_id)
        if task_kind == "cron_media_cleanup":
            return await self.executor.exec_cron_media_cleanup(session)
        if task_kind == "cron_media_sweep":
            await self.executor.exec_cron_media_sweep_stale(session)
            return []
        log.warning("billing-consumer: unknown task_kind=%s ref_id=%s", task_kind, ref_id)
        return []

    async def _handle_failure(self, task_id: int, exc: Exception) -> None:
        err_text = f"{type(exc).__name__}: {exc}"[:1000]
        try:
            async with self.sm() as session:
                task = await session.scalar(
                    select(ScheduledTaskModel)
                    .where(ScheduledTaskModel.id == task_id)
                    .with_for_update()
                )
                if task is None:
                    return
                task.attempts += 1
                task.last_error = err_text
                task.locked_until = None
                task.version += 1
                now = utc_now()
                task.updated_at = now

                if task.attempts >= task.max_attempts:
                    task.status = "dead"
                    await self.vk.xadd(
                        self.cfg.BILLING_QUEUE_DLQ,
                        {
                            "task_id": str(task.id),
                            "dedup_key": task.dedup_key or "",
                            "task_kind": task.task_kind,
                            "ref_id": str(task.ref_id or ""),
                            "member": task.dedup_key or f"task:{task.id}",
                            "attempts": str(task.attempts),
                            "error": err_text,
                            "at": now.isoformat(),
                        },
                        maxlen=1000,
                        approximate=True,
                    )
                    try:
                        await audit(
                            session,
                            action="tasks.dlq.enqueued",
                            target_type="dlq",
                            target_id=task.dedup_key or str(task.id),
                            result="warn",
                            meta={"task_id": task.id, "attempts": task.attempts, "queue": "billing"},
                        )
                    except Exception:  # noqa: BLE001
                        log.exception("billing-consumer: failed to audit DLQ")
                else:
                    backoff = _RETRY_BASE_SEC * (2 ** min(task.attempts - 1, 5))
                    task.status = "pending"
                    task.run_at = now + timedelta(seconds=backoff)

                await session.commit()
        except Exception:  # noqa: BLE001
            log.exception("billing-consumer: failed to persist failure for task=%s", task_id)


__all__ = ["BillingTaskConsumer"]
