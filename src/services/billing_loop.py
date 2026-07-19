"""Billing-loop: событийный планировщик истечений услуг и перепроверок платежей.

Не отдельный процесс, а набор функций внутри FastAPI-приложения (Event Producer).
Задачи хранятся **исключительно в Valkey** (sorted set по времени запуска) —
таблицы в БД нет. Очередь детерминированно пересобирается из ``user_services`` и
``user_payments`` при старте и пополняется по внешним событиям (создание/
продление услуги).

Очередь **разделяемая**: каждый инстанс billing засевает её и запускает свой
диспетчер. Выборка «созревших» задач атомарна — Lua-скрипт делает
``ZRANGEBYSCORE`` + ``ZREM`` одним вызовом, поэтому один и тот же член очереди не
достаётся двум инстансам одновременно (распределённый лок больше не нужен).

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
from models.system_settings import SystemSettingsMngr
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from services.audit import audit
from core.config import AppConfig
from utils.datetime_utils import utc_now
from lua.bus import LuaBus
from utils.retry import attempts, clear_attempts
from telemetry.task_log import TaskLog

log = logging.getLogger("saviorbill.billing")

# Префиксы членов очереди по виду задачи.
_SVC = "svc:"  # истечение услуги (ref = user_services.id)
_PAY = "pay:"  # перепроверка платежа (ref = user_payments.id)

# Атомарная выборка «созревших» задач: ZRANGEBYSCORE + ZREM одним вызовом, чтобы
# один и тот же член не достался двум инстансам billing одновременно.
_CLAIM_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
if #due > 0 then redis.call('ZREM', KEYS[1], unpack(due)) end
return due
"""


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
        task_log: TaskLog | None = None,
    ) -> None:
        self.engine = engine
        self.sm = sessionmaker
        self.vk = vk
        self.cfg = cfg
        self.task_log = task_log
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._stopped = False
        # Ограничитель параллелизма задач одной итерации (backpressure).
        self._sem = asyncio.Semaphore(cfg.BILLING_CONCURRENCY)

    # --- ресурсы -----------------------------------------------------------
    async def _bus(self, session: AsyncSession) -> LuaBus:
        """`LuaBus` с runtime-таймаутом/ретраями из `SystemSettingsMngr`.

        Тот же настраиваемый механизм, что и у request-scoped вызовов (см.
        `dependencies/lua.py::get_lua_bus_configured`) — фоновый billing-loop
        не должен вести себя иначе только потому, что у него нет HTTP-запроса.
        """
        settings = SystemSettingsMngr(
            session, self.vk, make_secbox(self.cfg), self.cfg.SETTINGS_CACHE_TTL
        )
        timeout = await settings.get_int(
            "lua.call_timeout_sec", self.cfg.LUA_CALL_TIMEOUT
        )
        max_retries = await settings.get_int("lua.max_retries", 2)
        backoff = await settings.get_int("lua.retry_backoff_sec", 5)
        return LuaBus(
            self.vk,
            self.cfg.LUA_TASK_STREAM,
            self.cfg.LUA_RESP_STREAM,
            default_timeout=timeout or self.cfg.LUA_CALL_TIMEOUT,
            max_retries=max_retries or 0,
            retry_backoff=backoff or 0,
            task_stream_maxlen=self.cfg.LUA_TASK_STREAM_MAXLEN,
            task_log=self.task_log,
            signing_key=self.cfg.BUS_SIGNING_KEY,
        )

    async def _pay_mngr(self, session: AsyncSession) -> PayMngr:
        return PayMngr(session, await self._bus(session), make_secbox(self.cfg))

    async def _usvc_mngr(self, session: AsyncSession) -> UserServicesMngr:
        return UserServicesMngr(
            session, await self._bus(session), make_secbox(self.cfg)
        )

    @property
    def _qkey(self) -> str:
        return self.cfg.BILLING_QUEUE_KEY

    # --- атомарная выборка созревших задач --------------------------------
    async def _claim_due(self, now: float, limit: int) -> list[str]:
        """Атомарно забрать «созревшие» задачи (ZRANGEBYSCORE + ZREM)."""
        raw = await self.vk.eval(_CLAIM_SCRIPT, 1, self._qkey, str(now), str(limit))
        return [r.decode() if isinstance(r, bytes) else r for r in (raw or [])]

    # --- жизненный цикл ----------------------------------------------------
    async def start(self) -> None:
        """Засеять разделяемую очередь и запустить фоновый диспетчер."""
        if not self.cfg.BILLING_LOOP_ENABLED:
            log.info("billing-loop is disabled (BILLING_LOOP_ENABLED=false)")
            return
        async with self.sm() as session:
            await self.seed_on_start(session)
        self._task = asyncio.create_task(self._run(), name="billing-loop")
        log.info("billing-loop launched")

    async def stop(self) -> None:
        """Остановить диспетчер."""
        self._stopped = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

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
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — цикл не должен падать
                log.exception("billing-loop: iteration error")
            await self._sleep_until_next()

    async def _tick(self) -> None:
        now = _score(utc_now())
        # Забираем задачи атомарно; членов больше нет в очереди после claim.
        due = await self._claim_due(now, self.cfg.BILLING_CONCURRENCY)
        if due:
            await asyncio.gather(*(self._process_one(member) for member in due))
        async with self.sm() as session:
            await self._refill(session)

    async def _process_one(self, member: str) -> None:
        """Обработать один claimed-член в отдельной сессии под семафором."""
        async with self._sem:
            async with self.sm() as session:
                try:
                    await self._execute(session, member)
                    await session.commit()
                except Exception:  # noqa: BLE001 — единичная задача не валит цикл
                    await session.rollback()
                    log.exception("billing-loop: %s task failed", member)

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
        # Член уже извлечён из очереди атомарным claim: повторный zrem не нужен.
        if member.startswith(_SVC):
            await self._exec_svc_action(session, int(member[len(_SVC) :]))
        elif member.startswith(_PAY):
            await self._exec_pay_recheck(session, int(member[len(_PAY) :]))
        # неизвестный член — уже удалён claim'ом, делать нечего.

    async def _exec_svc_action(self, session: AsyncSession, usvc_id: int) -> None:
        member = f"{_SVC}{usvc_id}"
        usvc = await session.get(UserServicesModel, usvc_id)
        if usvc is None or usvc.status != UsvcStatus.ACTIVE:
            # Член уже извлечён claim'ом — просто выходим.
            return
        # Срок ещё не наступил — перепланируем на актуальное время истечения.
        if usvc.expires_at is not None and usvc.expires_at > utc_now():
            await self.vk.zadd(self._qkey, {member: _score(usvc.expires_at)})
            return
        service = await session.get(ServiceModel, usvc.service_id)
        acc = await session.get(UserModel, usvc.account_id)
        try:
            mngr = await self._usvc_mngr(session)
            await mngr.expire(usvc, service, acc)
        except Exception:  # noqa: BLE001 — учёт попыток + DLQ, затем проброс
            await self._dlq_or_retry(member, f"svc:action:{usvc_id}", usvc_id)
            raise
        await self._clear_attempts(f"svc:action:{usvc_id}")
        await self._audit_expire(session, usvc, acc)

    async def _dlq_or_retry(self, member: str, attempt_key: str, ref_id: int) -> None:
        """Учесть попытку; при исчерпании — в DLQ, иначе вернуть задачу в очередь."""
        n, exhausted = await attempts(
            self.vk, attempt_key, self.cfg.BILLING_QUEUE_MAX_ATTEMPTS
        )
        if exhausted:
            await self.vk.xadd(
                self.cfg.BILLING_QUEUE_DLQ,
                {"member": member, "ref_id": str(ref_id), "attempts": str(n)},
            )
            await clear_attempts(self.vk, attempt_key)
        else:
            # Повтор через интервал перепроверки — задача снова в очереди.
            nxt = utc_now() + timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_INTERVAL)
            await self.vk.zadd(self._qkey, {member: _score(nxt)})

    async def _clear_attempts(self, attempt_key: str) -> None:
        await clear_attempts(self.vk, attempt_key)

    async def _audit_expire(
        self, session: AsyncSession, usvc: UserServicesModel, acc
    ) -> None:
        """Best-effort запись в аудит об истечении услуги."""
        try:
            await audit(
                session,
                action="service.expire",
                actor_id=getattr(acc, "id", None),
                target_type="user_service",
                target_id=str(usvc.id),
                meta={"service_id": usvc.service_id},
            )
        except Exception:  # noqa: BLE001 — аудит не должен ломать задачу
            log.exception("billing-loop: Failed to record expiration audit")

    async def _exec_pay_recheck(self, session: AsyncSession, pay_id: int) -> None:
        member = f"{_PAY}{pay_id}"
        payment = await session.get(UserPaymentsModel, pay_id)
        if payment is None or payment.status != PayStatus.PENDING:
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            return
        mngr = await self._pay_mngr(session)
        await mngr.recheck(payment)
        if payment.status != PayStatus.PENDING:
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            return
        # Всё ещё pending: считаем попытки, либо повторяем позже, либо → wait.
        attempts_n = await self.vk.hincrby(
            self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id), 1
        )
        if attempts_n >= self.cfg.BILLING_PAY_RECHECK_MAX:
            payment.status = PayStatus.WAIT
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
        else:
            nxt = utc_now() + timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_INTERVAL)
            await self.vk.zadd(self._qkey, {member: _score(nxt)})


__all__ = ["BillingLoop"]
