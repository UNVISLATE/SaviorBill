"""Billing-loop: in-process планировщик истечений услуг и перепроверок платежей.

Работает как Event Producer над таблицей-очередью ``billing_tasks``. Держит
«окно» ближайших задач: при старте засеивает просроченные и ближайшие, дальше
пополняет по мере разбора очереди и по внешним событиям (создание/продление
услуги). Один активный экземпляр гарантируется advisory-локом Postgres.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import valkey.asyncio as valkey
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.payment import PayMngr
from dependencies.usersvc import UserServicesMngr
from enums import (
    OrderStatus,
    PayStatus,
    ServiceAction,
    TaskKind,
    TaskStatus,
    UsvcState,
)
from models.billing_tasks import BillingTasksModel, BillingTasksMngr
from models.service import ServiceModel
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from utils.config import AppConfig
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus

log = logging.getLogger("saviorbill.billing")

# Ключ advisory-лока Postgres (единственный активный планировщик на кластер).
_LOCK_KEY = 0x5B0110


class BillingLoop:
    """Планировщик отложенных задач биллинга."""

    def __init__(
        self,
        engine: AsyncEngine,
        sessionmaker: async_sessionmaker[AsyncSession],
        vk: valkey.Valkey,
        cfg: AppConfig,
    ) -> None:
        self.engine = engine
        self.sm = sessionmaker
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._lock_conn = None
        self._wake = asyncio.Event()
        self._stopped = False

    # --- ресурсы -----------------------------------------------------------
    def _bus(self) -> LuaBus:
        return LuaBus(
            self.vk,
            self.cfg.LUA_TASK_STREAM,
            self.cfg.LUA_RESP_STREAM,
            self.cfg.LUA_CALL_TIMEOUT,
        )

    def _pay_mngr(self, session: AsyncSession) -> PayMngr:
        return PayMngr(session, self._bus(), make_secbox(self.cfg))

    def _usvc_mngr(self, session: AsyncSession) -> UserServicesMngr:
        return UserServicesMngr(session, self._bus())

    # --- жизненный цикл ----------------------------------------------------
    async def start(self) -> None:
        """Захватить advisory-лок, засеять очередь и запустить фоновый цикл."""
        if not self.cfg.BILLING_LOOP_ENABLED:
            log.info("billing-loop отключён (BILLING_LOOP_ENABLED=false)")
            return
        self._lock_conn = await self.engine.connect()
        got = await self._lock_conn.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}
        )
        if not got:
            log.info("billing-loop уже ведёт другой экземпляр — пассивный режим")
            await self._lock_conn.close()
            self._lock_conn = None
            return
        async with self.sm() as session:
            await self.seed_on_start(session)
            await session.commit()
        self._task = asyncio.create_task(self._run(), name="billing-loop")
        log.info("billing-loop запущен")

    async def stop(self) -> None:
        """Остановить цикл и освободить advisory-лок."""
        self._stopped = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._lock_conn is not None:
            try:
                await self._lock_conn.exec_driver_sql("SELECT 1")
                await self._lock_conn.scalar(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY}
                )
            except Exception:  # noqa: BLE001 — соединение могло закрыться
                pass
            await self._lock_conn.close()
            self._lock_conn = None

    def wake(self) -> None:
        """Разбудить цикл (после внешнего добавления задачи)."""
        self._wake.set()

    # --- сидинг / пополнение окна ------------------------------------------
    async def seed_on_start(self, session: AsyncSession) -> None:
        """Засеять окно: истёкшие/ближайшие услуги + висящие pending-платежи."""
        await self._refill(session)
        await self._seed_pending_payments(session)

    async def _refill(self, session: AsyncSession) -> int:
        """Поставить в очередь ближайшие активные срочные услуги без задачи.

        :return: сколько задач добавлено.
        """
        queued = select(BillingTasksModel.ref_id).where(
            BillingTasksModel.kind == TaskKind.SVC_ACTION,
            BillingTasksModel.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
        )
        rows = await session.scalars(
            select(UserServicesModel)
            .where(
                UserServicesModel.state == UsvcState.ACTIVE,
                UserServicesModel.expires_at.is_not(None),
                UserServicesModel.id.not_in(queued),
            )
            .order_by(UserServicesModel.expires_at)
            .limit(self.cfg.BILLING_QUEUE_WINDOW)
        )
        mngr = BillingTasksMngr(session)
        added = 0
        for usvc in rows:
            await mngr.add(
                TaskKind.SVC_ACTION,
                usvc.id,
                usvc.expires_at,
                action=ServiceAction.STOP,
            )
            added += 1
        return added

    async def _seed_pending_payments(self, session: AsyncSession) -> None:
        """Поставить перепроверку платежам, висящим в pending дольше порога."""
        threshold = utc_now() - timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_AFTER)
        queued = select(BillingTasksModel.ref_id).where(
            BillingTasksModel.kind == TaskKind.PAY_RECHECK,
            BillingTasksModel.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
        )
        rows = await session.scalars(
            select(UserPaymentsModel)
            .where(
                UserPaymentsModel.status == PayStatus.PENDING,
                UserPaymentsModel.created_at <= threshold,
                UserPaymentsModel.id.not_in(queued),
            )
            .order_by(UserPaymentsModel.created_at)
            .limit(self.cfg.BILLING_QUEUE_WINDOW)
        )
        mngr = BillingTasksMngr(session)
        for pay in rows:
            await mngr.add(TaskKind.PAY_RECHECK, pay.id, utc_now())

    # --- событийные хуки (вызываются из роутов) ----------------------------
    async def enqueue_service(self, usvc_id: int, run_at: datetime) -> None:
        """Поставить истечение услуги в очередь (при создании/продлении)."""
        async with self.sm() as session:
            mngr = BillingTasksMngr(session)
            if await mngr.pending_for(TaskKind.SVC_ACTION, usvc_id):
                return
            await mngr.add(
                TaskKind.SVC_ACTION, usvc_id, run_at, action=ServiceAction.STOP
            )
            await session.commit()
        self.wake()

    # --- основной цикл -----------------------------------------------------
    async def _run(self) -> None:
        while not self._stopped:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — цикл не должен падать
                log.exception("billing-loop: ошибка итерации")
            await self._sleep_until_next()

    async def _tick(self) -> None:
        async with self.sm() as session:
            due = await BillingTasksMngr(session).due(utc_now())
            for task in due:
                await self._execute(session, task)
            await self._refill(session)
            await session.commit()

    async def _sleep_until_next(self) -> None:
        self._wake.clear()
        async with self.sm() as session:
            nxt = await BillingTasksMngr(session).next_run_at()
        now = utc_now()
        if nxt is None:
            delay: float = self.cfg.BILLING_IDLE_SECONDS
        else:
            delay = max(0.0, (nxt - now).total_seconds())
            delay = min(delay, self.cfg.BILLING_IDLE_SECONDS)
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=max(delay, 0.5))
        except asyncio.TimeoutError:
            pass

    # --- исполнение задач --------------------------------------------------
    async def _execute(self, session: AsyncSession, task: BillingTasksModel) -> None:
        task.status = TaskStatus.RUNNING
        task.attempts += 1
        await session.flush()
        try:
            if task.kind == TaskKind.SVC_ACTION:
                await self._exec_svc_action(session, task)
            elif task.kind == TaskKind.PAY_RECHECK:
                await self._exec_pay_recheck(session, task)
            else:
                task.status = TaskStatus.FAILED
                task.last_error = f"неизвестный вид задачи: {task.kind}"
        except Exception as exc:  # noqa: BLE001 — ошибку фиксируем в задаче
            task.status = TaskStatus.FAILED
            task.last_error = str(exc)[:1024]
            log.exception("billing-loop: задача %s провалилась", task.id)
        await session.flush()

    async def _exec_svc_action(
        self, session: AsyncSession, task: BillingTasksModel
    ) -> None:
        usvc = await session.get(UserServicesModel, task.ref_id)
        if usvc is None or usvc.state != UsvcState.ACTIVE:
            task.status = TaskStatus.DONE
            return
        # Задача истечения актуальна только если срок реально наступил.
        if usvc.expires_at is not None and usvc.expires_at > utc_now():
            task.run_at = usvc.expires_at
            task.status = TaskStatus.QUEUED
            return
        service = await session.get(ServiceModel, usvc.service_id)
        acc = await session.get(UserModel, usvc.account_id)
        await self._usvc_mngr(session).expire(usvc, service, acc)
        task.status = TaskStatus.DONE

    async def _exec_pay_recheck(
        self, session: AsyncSession, task: BillingTasksModel
    ) -> None:
        payment = await session.get(UserPaymentsModel, task.ref_id)
        if payment is None or payment.status != PayStatus.PENDING:
            task.status = TaskStatus.DONE
            return
        await self._pay_mngr(session).recheck(payment)
        if payment.status != PayStatus.PENDING:
            task.status = TaskStatus.DONE
            return
        # Всё ещё pending: либо повторяем позже, либо переводим в wait.
        if task.attempts >= self.cfg.BILLING_PAY_RECHECK_MAX:
            payment.status = PayStatus.WAIT
            task.status = TaskStatus.WAIT
        else:
            task.run_at = utc_now() + timedelta(
                seconds=self.cfg.BILLING_PAY_RECHECK_INTERVAL
            )
            task.status = TaskStatus.QUEUED


__all__ = ["BillingLoop"]
