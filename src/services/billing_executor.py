"""Доменный исполнитель фоновых задач биллинга (без цикла поллинга БД)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import valkey.asyncio as valkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import AppConfig
from dependencies.mail import build_mail_svc
from dependencies.payment import PayMngr
from dependencies.sec import make_secbox
from dependencies.triggers import build_dispatcher
from dependencies.usersvc import UserServicesMngr
from enums import PayStatus, ServiceAction, UsvcStatus
from lua.bus import LuaBus
from messaging.mediabus import MediaBus
from models.service import ServiceModel
from models.system_media import SystemMediaMngr, all_storage_keys
from models.system_settings import SystemSettingsMngr
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from models.worker_jobs import WorkerJobsMngr
from services.account import lock_account
from services.audit import audit
from services.fx import FxRates
from services.scheduler_outbox import (
    schedule_delivery_retry,
    schedule_payment_recheck,
    schedule_provision_poll,
    schedule_service_expire,
)
from telemetry.task_log import TaskLog
from utils.datetime_utils import utc_now

log = logging.getLogger("saviorbill.billing.executor")

_DELIVERY_MAX_ATTEMPTS = 3
_DELIVERY_BACKOFF_SEC = 60
_DEFAULT_STALE_JOB_SEC = 300


class BillingExecutor:
    """Чистая доменная логика исполнения отложенных и периодических задач."""

    def __init__(
        self,
        vk: valkey.Valkey,
        cfg: AppConfig,
        task_log: TaskLog | None = None,
    ) -> None:
        self.vk = vk
        self.cfg = cfg
        self.task_log = task_log

    # --- зависимости для транзакции ----------------------------------------
    async def _bus(self, session: AsyncSession) -> LuaBus:
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

    async def _dispatcher(self, session: AsyncSession):
        settings = SystemSettingsMngr(
            session, self.vk, make_secbox(self.cfg), self.cfg.SETTINGS_CACHE_TTL
        )
        bus = await self._bus(session)
        return build_dispatcher(
            session, settings, bus, await build_mail_svc(settings), self.cfg
        )

    async def _pay_mngr(self, session: AsyncSession) -> PayMngr:
        box = make_secbox(self.cfg)
        settings = SystemSettingsMngr(
            session, self.vk, box, self.cfg.SETTINGS_CACHE_TTL
        )
        bus = await self._bus(session)
        dispatcher = await self._dispatcher(session)
        return PayMngr(
            session,
            bus,
            box,
            dispatcher,
            FxRates(settings, self.vk, bus=bus, session=session, box=box),
        )

    async def _usvc_mngr(self, session: AsyncSession) -> UserServicesMngr:
        dispatcher = await self._dispatcher(session)
        return UserServicesMngr(
            session, await self._bus(session), make_secbox(self.cfg), dispatcher=dispatcher
        )

    def media_bus(self) -> MediaBus:
        return MediaBus(
            self.vk,
            self.cfg.MEDIA_TASK_STREAM,
            self.cfg.MEDIA_TASK_STREAM_MAXLEN,
            signing_key=self.cfg.BUS_SIGNING_KEY,
        )

    # --- истечение услуги --------------------------------------------------
    async def exec_svc_expire(self, session: AsyncSession, usvc_id: int) -> None:
        usvc = await session.scalar(
            select(UserServicesModel)
            .where(UserServicesModel.id == usvc_id)
            .with_for_update(of=UserServicesModel)
        )
        if usvc is None or usvc.status not in (UsvcStatus.ACTIVE, UsvcStatus.STOPPED):
            return
        if usvc.expires_at is not None and usvc.expires_at > utc_now():
            await schedule_service_expire(session, usvc_id, usvc.expires_at)
            return
        service = await session.get(ServiceModel, usvc.service_id)
        acc = await session.get(UserModel, usvc.account_id)
        mngr = await self._usvc_mngr(session)
        await mngr.expire(usvc, service, acc)
        await self._audit_expire(session, usvc, acc)

    async def _audit_expire(
        self, session: AsyncSession, usvc: UserServicesModel, acc: UserModel | None
    ) -> None:
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
            log.exception("billing-executor: Failed to record expiration audit")

    # --- перепроверка платежа ----------------------------------------------
    async def exec_pay_recheck(self, session: AsyncSession, pay_id: int) -> None:
        payment = await session.get(UserPaymentsModel, pay_id)
        if payment is None or payment.status != PayStatus.PENDING:
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            return
        mngr = await self._pay_mngr(session)
        await mngr.recheck(payment)
        if payment.status != PayStatus.PENDING:
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
            if (
                payment.status == PayStatus.PAID
                and payment.user_svc_id is not None
            ):
                usvc = await session.get(UserServicesModel, payment.user_svc_id)
                if usvc is not None and usvc.status == UsvcStatus.ACTIVE and usvc.expires_at:
                    await schedule_service_expire(session, usvc.id, usvc.expires_at)
                elif usvc is not None and usvc.status == UsvcStatus.FAILED:
                    await schedule_delivery_retry(session, usvc.id, utc_now())
            return

        attempts_n = await self.vk.hincrby(
            self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id), 1
        )
        if attempts_n >= self.cfg.BILLING_PAY_RECHECK_MAX:
            payment.status = PayStatus.WAIT
            await self.vk.hdel(self.cfg.BILLING_ATTEMPTS_KEY, str(pay_id))
        else:
            nxt = utc_now() + timedelta(seconds=self.cfg.BILLING_PAY_RECHECK_INTERVAL)
            await schedule_payment_recheck(session, pay_id, nxt)

    # --- повтор проваленной выдачи услуги ----------------------------------
    async def _delivery_limits(self, session: AsyncSession) -> tuple[int, int]:
        settings = SystemSettingsMngr(
            session, self.vk, make_secbox(self.cfg), self.cfg.SETTINGS_CACHE_TTL
        )
        max_attempts = await settings.get_int(
            "orders.delivery.max_attempts", _DELIVERY_MAX_ATTEMPTS
        )
        backoff = await settings.get_int(
            "orders.delivery.retry_backoff_sec", _DELIVERY_BACKOFF_SEC
        )
        return (
            max_attempts or _DELIVERY_MAX_ATTEMPTS,
            backoff or _DELIVERY_BACKOFF_SEC,
        )

    async def exec_delivery_retry(self, session: AsyncSession, usvc_id: int) -> None:
        row = await session.get(UserServicesModel, usvc_id)
        if (
            row is None
            or row.status != UsvcStatus.FAILED
            or (row.private_data or {}).get("delivery_credit")
        ):
            return
        acc = await lock_account(session, row.account_id)
        usvc = await session.get(UserServicesModel, usvc_id, with_for_update=True)
        if (
            usvc is None
            or usvc.status != UsvcStatus.FAILED
            or acc is None
            or (usvc.private_data or {}).get("delivery_credit")
        ):
            return
        max_attempts, backoff = await self._delivery_limits(session)

        if usvc.delivery_attempts < max_attempts:
            service = await session.get(ServiceModel, usvc.service_id)
            if service is None:
                return
            mngr = await self._usvc_mngr(session)
            await mngr.deliver(usvc, service, acc)
            if usvc.status == UsvcStatus.ACTIVE:
                if usvc.expires_at is not None:
                    await schedule_service_expire(session, usvc.id, usvc.expires_at)
                await self._audit_delivery(session, usvc, "service.delivery.recovered")
                return
            if usvc.delivery_attempts < max_attempts:
                nxt = utc_now() + timedelta(seconds=backoff)
                await schedule_delivery_retry(session, usvc_id, nxt)
                return

        await self._compensate_delivery(session, usvc)

    # --- асинхронный провижининг (poll) ------------------------------------
    async def exec_svc_provision_poll(self, session: AsyncSession, usvc_id: int) -> None:
        row = await session.get(UserServicesModel, usvc_id)
        if row is None or row.status != UsvcStatus.PROVISIONING:
            return
        acc = await lock_account(session, row.account_id)
        usvc = await session.get(UserServicesModel, usvc_id, with_for_update=True)
        if usvc is None or usvc.status != UsvcStatus.PROVISIONING or acc is None:
            return

        priv = dict(usvc.private_data or {})
        poll_cfg = dict(priv.get("_provisioning") or {})
        attempts = int(poll_cfg.get("attempts", 0))
        max_attempts = int(poll_cfg.get("max_attempts", 20))
        interval = max(5, min(int(poll_cfg.get("interval_sec", 15)), 300))
        backoff = str(poll_cfg.get("backoff", "fixed"))
        poll_action = str(poll_cfg.get("action") or ServiceAction.POLL)

        deadline_raw = poll_cfg.get("deadline_at")
        deadline_exceeded = False
        if isinstance(deadline_raw, str):
            try:
                dl = datetime.fromisoformat(deadline_raw)
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                deadline_exceeded = utc_now() >= dl
            except ValueError:
                deadline_exceeded = False

        if attempts >= max_attempts or deadline_exceeded:
            priv.pop("_provisioning", None)
            usvc.private_data = priv
            usvc.status = UsvcStatus.FAILED
            usvc.error = "provisioning timed out"
            await self._compensate_delivery(session, usvc)
            await self._audit_delivery(
                session, usvc, "service.provisioning.timeout", meta={"attempts": attempts}
            )
            return

        service = await session.get(ServiceModel, usvc.service_id)
        if service is None:
            return

        mngr = await self._usvc_mngr(session)
        try:
            await mngr.run_action(usvc, service, acc, poll_action)
        except Exception as exc:  # noqa: BLE001
            p_after = dict(usvc.private_data or {})
            p_after.pop("_provisioning", None)
            usvc.private_data = p_after
            usvc.status = UsvcStatus.FAILED
            usvc.error = str(exc)[:512]
            await self._compensate_delivery(session, usvc)
            await self._audit_delivery(
                session, usvc, "service.provisioning.failed", meta={"error": usvc.error}
            )
            return

        if usvc.status == UsvcStatus.PROVISIONING:
            p_after = dict(usvc.private_data or {})
            cfg_after = dict(p_after.get("_provisioning") or poll_cfg)
            next_attempts = attempts + 1
            cfg_after["attempts"] = next_attempts
            p_after["_provisioning"] = cfg_after
            usvc.private_data = p_after

            base_interval = max(5, min(int(cfg_after.get("interval_sec", interval)), 300))
            delay = (
                min(base_interval * (2 ** min(next_attempts, 5)), 300)
                if backoff == "exponential"
                else base_interval
            )
            await schedule_provision_poll(
                session, usvc.id, utc_now() + timedelta(seconds=delay)
            )
            return

        if usvc.status == UsvcStatus.ACTIVE:
            usvc.delivered_at = utc_now()
            usvc.error = None
            mngr._apply_default_expiry(usvc)
            await mngr._credit_referral(acc, service, usvc.price)
            if usvc.expires_at is not None:
                await schedule_service_expire(session, usvc.id, usvc.expires_at)
            await self._audit_delivery(
                session, usvc, "service.provisioning.completed", meta={"attempts": attempts + 1}
            )

    async def _compensate_delivery(
        self, session: AsyncSession, usvc: UserServicesModel
    ) -> None:
        locked = (
            await session.get(UserServicesModel, usvc.id, with_for_update=True)
            if hasattr(session, "get")
            else None
        )
        if locked is not None:
            usvc = locked
        private = usvc.private_data or {}
        if private.get("delivery_credit"):
            return
        acc = await lock_account(session, usvc.account_id)
        if acc is None or usvc.price <= 0:
            return
        charged_bonus = Decimal(str(private.get("charged_bonus", "0")))
        charged_balance = Decimal(str(private.get("charged_balance", "0")))
        if charged_bonus > 0 or charged_balance > 0:
            if hasattr(acc, "bonus_balance"):
                acc.bonus_balance += charged_bonus
            acc.balance += charged_balance
        else:
            acc.balance += usvc.price
        usvc.private_data = {
            **private,
            "delivery_credit": {
                "amount": str(usvc.price),
                "bonus": str(charged_bonus),
                "balance": str(
                    charged_balance
                    if (charged_bonus > 0 or charged_balance > 0)
                    else usvc.price
                ),
                "at": utc_now().isoformat(),
            },
        }
        await session.flush()
        await self._audit_delivery(
            session,
            usvc,
            "service.delivery.credited",
            meta={"amount": str(usvc.price), "attempts": usvc.delivery_attempts},
        )

    async def _audit_delivery(
        self,
        session: AsyncSession,
        usvc: UserServicesModel,
        action: str,
        meta: dict | None = None,
    ) -> None:
        try:
            await audit(
                session,
                action=action,
                actor_id=usvc.account_id,
                target_type="user_service",
                target_id=str(usvc.id),
                meta={"service_id": usvc.service_id, **(meta or {})},
            )
        except Exception:  # noqa: BLE001
            log.exception("billing-executor: failed to record %s audit", action)

    # --- дедлайн подтверждения кандидата медиа ----------------------------
    async def exec_media_expire(
        self, session: AsyncSession, media_id: int
    ) -> list[tuple[str, list[str]]]:
        """Удалить неподтверждённого кандидата медиа.

        Возвращает список ``(backend, keys)``, который вызывающий код должен
        поставить в ``MediaBus.enqueue_delete`` строго после ``session.commit()``.
        """
        mngr = SystemMediaMngr(session)
        media = await mngr.by_id(media_id)
        if media is None:
            return []
        is_avatar = await session.scalar(
            select(UserModel.id).where(UserModel.avatar_media_id == media_id).limit(1)
        )
        if is_avatar is not None:
            await mngr.confirm(media)
            return []
        backend = media.backend
        keys = all_storage_keys(media)
        await mngr.delete(media)
        log.info("billing-executor: unconfirmed avatar candidate media=%s expired", media_id)
        return [(backend, keys)]

    # --- периодические cron-задачи от scheduler ----------------------------
    async def exec_cron_media_cleanup(
        self, session: AsyncSession
    ) -> list[tuple[str, list[str]]]:
        settings = SystemSettingsMngr(
            session, self.vk, make_secbox(self.cfg), self.cfg.SETTINGS_CACHE_TTL
        )
        grace = await settings.get_int("media.cleanup_grace_sec", 3600)
        mngr = SystemMediaMngr(session)
        orphans = await mngr.orphans(grace_sec=grace or 0)
        if not orphans:
            return []
        to_delete = [(m.backend, all_storage_keys(m)) for m in orphans]
        for media in orphans:
            await mngr.delete(media)
        return to_delete

    async def exec_cron_media_sweep_stale(self, session: AsyncSession) -> int:
        jobs = WorkerJobsMngr(session)
        stale_sec = int(getattr(self.cfg, "MEDIA_JOB_STALE_AFTER_SEC", _DEFAULT_STALE_JOB_SEC) or _DEFAULT_STALE_JOB_SEC)
        return await jobs.sweep_stale(timedelta(seconds=stale_sec))


__all__ = ["BillingExecutor"]
