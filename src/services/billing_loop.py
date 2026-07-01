"""Billing-loop: событийный планировщик истечений услуг и перепроверок платежей.

Не отдельный процесс, а набор функций внутри FastAPI-приложения (Event Producer).
Задачи хранятся **исключительно в Valkey** (sorted set по времени запуска) —
таблицы в БД нет. Очередь детерминированно пересобирается из ``user_services`` и
``user_payments`` при старте и пополняется по внешним событиям (создание/
продление услуги). Единственный активный экземпляр гарантируется распределённым
локом ``SET NX`` с TTL.

Идемпотентность: член очереди детерминирован (``svc:<id>`` / ``pay:<id>``), поэтому
повторный засев (новый инстанс/рестарт) не плодит дубликатов.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import valkey.asyncio as valkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.payment import PayMngr
from dependencies.usersvc import UserServicesMngr
from enums import PayStatus, UsvcStatus
from models.service import ServiceModel
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from utils.config import AppConfig
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus

log = logging.getLogger("saviorbill.billing")

# Префиксы членов очереди по виду задачи.
_SVC = "svc:"  # истечение услуги (ref = user_services.id)
_PAY = "pay:"  # перепроверка платежа (ref = user_payments.id)


def _score(dt: datetime) -> float:
    """Unix-время запуска задачи как score сортированного множества."""
    return dt.timestamp()


class BillingLoop:
    """Событийный планировщик задач биллинга поверх Valkey."""

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
        self._wake = asyncio.Event()
        self._stopped = False
        self._has_lock = False
        # Уникальный токен владельца лока (для безопасного освобождения).
        self._lock_token = f"{id(self)}-{utc_now().timestamp()}"

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

    @property
    def _qkey(self) -> str:
        return self.cfg.BILLING_QUEUE_KEY

    # --- распределённый лок (SET NX + TTL) --------------------------------
    async def _acquire_lock(self) -> bool:
        return bool(
            await self.vk.set(
                self.cfg.BILLING_LOCK_KEY,
                self._lock_token,
                nx=True,
                ex=self.cfg.BILLING_LOCK_TTL,
            )
        )

    async def _renew_lock(self) -> bool:
        """Продлить лок, только если он всё ещё наш. Возвращает удержание."""
        cur = await self.vk.get(self.cfg.BILLING_LOCK_KEY)
        token = cur.decode() if isinstance(cur, bytes) else cur
        if token != self._lock_token:
            return False
        await self.vk.expire(self.cfg.BILLING_LOCK_KEY, self.cfg.BILLING_LOCK_TTL)
        return True

    async def _release_lock(self) -> None:
        cur = await self.vk.get(self.cfg.BILLING_LOCK_KEY)
        token = cur.decode() if isinstance(cur, bytes) else cur
        if token == self._lock_token:
            await self.vk.delete(self.cfg.BILLING_LOCK_KEY)

    # --- жизненный цикл ----------------------------------------------------
    async def start(self) -> None:
        """Захватить лок, засеять очередь и запустить фоновый цикл."""
        if not self.cfg.BILLING_LOOP_ENABLED:
            log.info("billing-loop отключён (BILLING_LOOP_ENABLED=false)")
            return
        if not await self._acquire_lock():
            log.info("billing-loop уже ведёт другой экземпляр — пассивный режим")
            return
        self._has_lock = True
        async with self.sm() as session:
            await self.seed_on_start(session)
        self._task = asyncio.create_task(self._run(), name="billing-loop")
        log.info("billing-loop запущен")

    async def stop(self) -> None:
        """Остановить цикл и освободить лок."""
        self._stopped = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._has_lock:
            try:
                await self._release_lock()
            except Exception:  # noqa: BLE001 — соединение могло закрыться
                pass
            self._has_lock = False

    def wake(self) -> None:
        """Разбудить цикл (после внешнего добавления задачи)."""
        self._wake.set()

    # --- засев очереди -----------------------------------------------------
    async def seed_on_start(self, session: AsyncSession) -> None:
        """Засеять окно: истёкшие/ближайшие услуги + висящие pending-платежи."""
        await self._refill(session)
        await self._seed_pending_payments(session)

    async def _refill(self, session: AsyncSession) -> int:
        """Поставить ближайшие активные срочные услуги в очередь. Идемпотентно.

        Услуги со статусом ACTIVE и истёкшим сроком попадут со score в прошлом
        и будут обработаны немедленно; активные с будущим сроком — по времени.

        :return: сколько членов добавлено/обновлено.
        """
        rows = await session.scalars(
            select(UserServicesModel)
            .where(
                UserServicesModel.status == UsvcStatus.ACTIVE,
                UserServicesModel.expires_at.is_not(None),
            )
            .order_by(UserServicesModel.expires_at)
            .limit(self.cfg.BILLING_QUEUE_WINDOW)
        )
        added = 0
        for usvc in rows:
            await self.vk.zadd(
                self._qkey, {f"{_SVC}{usvc.id}": _score(usvc.expires_at)}
            )
            added += 1
        return added

    async def _seed_pending_payments(self, session: AsyncSession) -> None:
        """Поставить перепроверку платежам, висящим в pending дольше порога."""
        threshold = utc_now() - timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_AFTER)
        rows = await session.scalars(
            select(UserPaymentsModel)
            .where(
                UserPaymentsModel.status == PayStatus.PENDING,
                UserPaymentsModel.created_at <= threshold,
            )
            .order_by(UserPaymentsModel.created_at)
            .limit(self.cfg.BILLING_QUEUE_WINDOW)
        )
        now = _score(utc_now())
        for pay in rows:
            await self.vk.zadd(self._qkey, {f"{_PAY}{pay.id}": now})

    async def enqueue_service(self, usvc_id: int, run_at: datetime) -> None:
        """Поставить истечение услуги в очередь (при создании/продлении).

        :arg usvc_id: id выданной услуги.
        :arg run_at: момент истечения (когда выполнять действие).
        """
        await self.vk.zadd(self._qkey, {f"{_SVC}{usvc_id}": _score(run_at)})
        self.wake()

    # --- основной цикл -----------------------------------------------------
    async def _run(self) -> None:
        while not self._stopped:
            try:
                if not await self._renew_lock():
                    log.warning("billing-loop: лок утерян, останавливаюсь")
                    break
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — цикл не должен падать
                log.exception("billing-loop: ошибка итерации")
            await self._sleep_until_next()

    async def _tick(self) -> None:
        now = _score(utc_now())
        due = await self.vk.zrangebyscore(self._qkey, "-inf", now)
        for raw in due:
            member = raw.decode() if isinstance(raw, bytes) else raw
            async with self.sm() as session:
                try:
                    await self._execute(session, member)
                    await session.commit()
                except Exception:  # noqa: BLE001 — единичная задача не валит цикл
                    await session.rollback()
                    log.exception("billing-loop: задача %s провалилась", member)
        async with self.sm() as session:
            await self._refill(session)

    async def _sleep_until_next(self) -> None:
        self._wake.clear()
        head = await self.vk.zrange(self._qkey, 0, 0, withscores=True)
        now = utc_now().timestamp()
        if not head:
            delay: float = self.cfg.BILLING_IDLE_SECONDS
        else:
            nxt = head[0][1]
            delay = max(0.0, nxt - now)
            delay = min(delay, self.cfg.BILLING_IDLE_SECONDS)
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=max(delay, 0.5))
        except asyncio.TimeoutError:
            pass

    # --- исполнение задач --------------------------------------------------
    async def _execute(self, session: AsyncSession, member: str) -> None:
        if member.startswith(_SVC):
            await self._exec_svc_action(session, int(member[len(_SVC) :]))
        elif member.startswith(_PAY):
            await self._exec_pay_recheck(session, int(member[len(_PAY) :]))
        else:  # неизвестный член — просто убираем
            await self.vk.zrem(self._qkey, member)

    async def _exec_svc_action(self, session: AsyncSession, usvc_id: int) -> None:
        member = f"{_SVC}{usvc_id}"
        usvc = await session.get(UserServicesModel, usvc_id)
        if usvc is None or usvc.status != UsvcStatus.ACTIVE:
            await self.vk.zrem(self._qkey, member)
            return
        # Срок ещё не наступил — перепланируем на актуальное время истечения.
        if usvc.expires_at is not None and usvc.expires_at > utc_now():
            await self.vk.zadd(self._qkey, {member: _score(usvc.expires_at)})
            return
        service = await session.get(ServiceModel, usvc.service_id)
        acc = await session.get(UserModel, usvc.account_id)
        await self._usvc_mngr(session).expire(usvc, service, acc)
        await self.vk.zrem(self._qkey, member)

    async def _exec_pay_recheck(self, session: AsyncSession, pay_id: int) -> None:
        member = f"{_PAY}{pay_id}"
        payment = await session.get(UserPaymentsModel, pay_id)
        if payment is None or payment.status != PayStatus.PENDING:
            await self.vk.zrem(self._qkey, member)
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            return
        await self._pay_mngr(session).recheck(payment)
        if payment.status != PayStatus.PENDING:
            await self.vk.zrem(self._qkey, member)
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            return
        # Всё ещё pending: считаем попытки, либо повторяем позже, либо → wait.
        attempts = await self.vk.hincrby(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id), 1)
        if attempts >= self.cfg.BILLING_PAY_RECHECK_MAX:
            payment.status = PayStatus.WAIT
            await self.vk.zrem(self._qkey, member)
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
        else:
            nxt = utc_now() + timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_INTERVAL)
            await self.vk.zadd(self._qkey, {member: _score(nxt)})


__all__ = ["BillingLoop"]
