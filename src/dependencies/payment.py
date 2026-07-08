"""Платежи через провайдеров: инициализация, вебхук, перепроверка, возврат.

У каждого провайдера один action-driven Lua-скрипт: одно тело обрабатывает
все действия платежа (``create``/``callback``/``check``/``refund``) — какие
именно поддержаны, скрипт объявляет в ``lua_scripts.actions``.
"""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.lua import get_lua_bus_configured
from dependencies.sec import make_secbox
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr
from enums import PayAction, PayStatus, PayTarget
from integrations.triggers import TriggerDispatcher, TriggerEvent
from models.payment_providers import PaymentProvidersModel, PaymentProvidersMngr
from models.service import ServiceModel
from models.system_scripts import SystemScriptsModel
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from schemas.lua import LuaRequest
from services.audit import audit
from services.lua_ctx import LuaRunner
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus
from utils.sec.box import SecBox


class PayMngr:
    """Создание платежей и обработка событий платежа через скрипт провайдера."""

    def __init__(
        self,
        session: AsyncSession,
        bus: LuaBus,
        box: SecBox,
        dispatcher: TriggerDispatcher | None = None,
    ) -> None:
        self.s = session
        self.bus = bus
        self.box = box
        self.runner = LuaRunner(bus)
        self.dispatcher = dispatcher

    # --- доступ к провайдеру/секретам/скрипту ----------------------------
    async def _provider(
        self, slug: str, *, enabled: bool = True
    ) -> PaymentProvidersModel:
        stmt = select(PaymentProvidersModel).where(PaymentProvidersModel.slug == slug)
        if enabled:
            stmt = stmt.where(PaymentProvidersModel.enabled.is_(True))
        prov = await self.s.scalar(stmt)
        if prov is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "платёжный провайдер не найден"
            )
        return prov

    def _secrets(self, prov: PaymentProvidersModel) -> dict:
        """Расшифровать и распарсить JSON секретов провайдера."""
        if not prov.secrets_enc:
            return {}
        raw = self.box.open(prov.secrets_enc)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    async def _script(
        self, prov: PaymentProvidersModel, action: str
    ) -> SystemScriptsModel:
        """Получить action-driven скрипт провайдера и проверить поддержку действия.

        :arg prov: провайдер.
        :arg action: требуемое действие (см. :class:`enums.PayAction`).
        :raises HTTPException: скрипт не задан/недоступен/не поддерживает действие.
        """
        if not prov.script_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "у провайдера не задан платёжный скрипт"
            )
        script = await self.s.get(SystemScriptsModel, prov.script_id)
        if script is None or not script.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "платёжный скрипт провайдера недоступен"
            )
        supported = script.actions or []
        if supported and action not in supported:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"скрипт провайдера не поддерживает действие «{action}»",
            )
        return script

    # --- инициализация платежа -------------------------------------------
    async def create(
        self,
        acc: UserModel,
        amount: Decimal,
        provider_slug: str,
        *,
        target: str = PayTarget.BALANCE,
        user_svc_id: int | None = None,
        currency: str | None = None,
        return_url: str | None = None,
    ) -> UserPaymentsModel:
        """Создать платёж и запустить скрипт (action=create) за ссылкой оплаты."""
        prov = await self._provider(provider_slug)
        script = await self._script(prov, PayAction.CREATE)
        secrets = self._secrets(prov)

        payment = UserPaymentsModel(
            account_id=acc.id,
            provider=prov.slug,
            amount=amount,
            currency=currency or prov.currency,
            status=PayStatus.PENDING,
            target=target,
            user_svc_id=user_svc_id,
        )
        self.s.add(payment)
        await self.s.flush()

        try:
            res = await self.runner.run_payment(
                script,
                PayAction.CREATE,
                acc,
                payment,
                prov,
                secrets,
                return_url=return_url,
            )
            payment.public_data = res.get("public") or {}
            payment.private_data = res.get("private") or {}
            payment.external_id = (res.get("private") or {}).get("external_id")
        except Exception as exc:  # noqa: BLE001
            payment.status = PayStatus.FAILED
            payment.private_data = {"error": str(exc)[:512]}

        await self.s.flush()
        return payment

    # --- обработка вебхука -------------------------------------------------
    async def callback(
        self, provider_slug: str, request: LuaRequest
    ) -> UserPaymentsModel:
        """Обработать входящий вебхук провайдера (доверенный сервер-сервер).

        Скрипт сам проверяет подпись/ключ и возвращает результат в ``private``;
        мы полагаемся на его ответ без самостоятельной перепроверки апстрима.

        :arg provider_slug: slug провайдера из пути колбэка (статичный URL).
        :arg request: данные входящего запроса (метод/ip/заголовки/query/тело).
        :return: обновлённый платёж.
        """
        prov = await self._provider(provider_slug)
        script = await self._script(prov, PayAction.CALLBACK)
        res = await self.runner.run_payment(
            script,
            PayAction.CALLBACK,
            _blank_account(),
            _blank_payment(prov.slug),
            prov,
            self._secrets(prov),
            request=request,
        )
        priv = res.get("private") or {}

        if not priv.get("ok"):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "колбэк не прошёл проверку"
            )

        # Блокируем строку платежа на время мутации: сеть/скрипт уже
        # отработали выше без удержания лока, а сам commit/settle идёт под
        # ним — исключает гонку с параллельным recheck/refund/повторным
        # вебхуком одного и того же платежа.
        payment = await self._locate(priv, provider_slug, for_update=True)
        if payment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "платёж не найден")
        if payment.status in (PayStatus.PAID, PayStatus.REFUNDED):
            return payment  # идемпотентность

        if priv.get("paid"):
            await self._settle(payment, priv)
        elif priv.get("refunded") and payment.status == PayStatus.PAID:
            await self._apply_refund(payment, priv)
        elif priv.get("failed"):
            payment.status = PayStatus.FAILED

        if res.get("public"):
            payment.public_data = {**(payment.public_data or {}), **res["public"]}
        payment.private_data = {**(payment.private_data or {}), **priv}

        await self.s.flush()
        return payment

    async def recheck(self, payment: UserPaymentsModel) -> UserPaymentsModel:
        """Перепроверить статус платежа у провайдера (action=check).

        В отличие от вебхука, инициируем сверку сами: скрипт по ``action=check``
        обращается к API провайдера. Успех → ``_settle``; явный отказ →
        ``failed``; неопределённость → платёж остаётся ``pending``.

        :arg payment: платёж для перепроверки.
        :return: обновлённый платёж.
        """
        if payment.status in (PayStatus.PAID, PayStatus.FAILED, PayStatus.REFUNDED):
            return payment
        prov = await self._provider(payment.provider, enabled=False)
        script = await self._script(prov, PayAction.CHECK)
        acc = await self.s.get(UserModel, payment.account_id)

        res = await self.runner.run_payment(
            script,
            PayAction.CHECK,
            acc,
            payment,
            prov,
            self._secrets(prov),
        )
        priv = res.get("private") or {}

        # Перечитываем и блокируем платёж перед мутацией: пока мы ждали
        # ответ скрипта (сеть), его мог обработать параллельный
        # callback/recheck/refund.
        payment = await self.s.get(
            UserPaymentsModel, payment.id, with_for_update=True
        )
        if payment.status in (PayStatus.PAID, PayStatus.FAILED, PayStatus.REFUNDED):
            return payment

        if priv.get("ok") and priv.get("paid"):
            await self._settle(payment, priv)
        elif priv.get("ok") and priv.get("failed"):
            payment.status = PayStatus.FAILED

        if res.get("public"):
            payment.public_data = {**(payment.public_data or {}), **res["public"]}
        payment.private_data = {**(payment.private_data or {}), **priv}
        await self.s.flush()
        return payment

    async def refund(self, payment: UserPaymentsModel) -> UserPaymentsModel:
        """Вернуть средства по платежу (action=refund).

        :arg payment: оплаченный платёж для возврата.
        :return: обновлённый платёж.
        """
        if payment.status != PayStatus.PAID:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "возврат возможен только для оплаченного"
            )
        prov = await self._provider(payment.provider, enabled=False)
        script = await self._script(prov, PayAction.REFUND)
        acc = await self.s.get(UserModel, payment.account_id)

        res = await self.runner.run_payment(
            script,
            PayAction.REFUND,
            acc,
            payment,
            prov,
            self._secrets(prov),
        )
        priv = res.get("private") or {}

        # Как и в recheck — блокируем и перечитываем статус перед мутацией
        # (сеть к провайдеру уже отработала без удержания лока).
        payment = await self.s.get(
            UserPaymentsModel, payment.id, with_for_update=True
        )
        if payment.status != PayStatus.PAID:
            return payment  # уже обработан конкурентным запросом — идемпотентно

        if priv.get("ok") and priv.get("refunded"):
            await self._apply_refund(payment, priv)
        if res.get("public"):
            payment.public_data = {**(payment.public_data or {}), **res["public"]}
        payment.private_data = {**(payment.private_data or {}), **priv}
        await self.s.flush()
        return payment

    async def _apply_refund(self, payment: UserPaymentsModel, priv: dict) -> None:
        """Применить рефанд: пометить ``REFUNDED``, откатить услугу/ключ и
        списать баланс в пределах суммы этого платежа (см. IMPLEMENTATION_PLAN.md §2).

        Рефанд не поддерживает частичные суммы — либо весь платёж возвращён,
        либо нет. Но откат выданного по нему (услуга/ключ/баланс) — не
        "партиальный рефанд", а обязательное следствие возврата денег за
        этот конкретный платёж.

        :arg payment: платёж, для которого провайдер подтвердил возврат.
        :arg priv: приватные данные ответа скрипта (для дальнейшего merge).
        """
        if payment.status == PayStatus.REFUNDED:
            return
        payment.status = PayStatus.REFUNDED

        if payment.target == PayTarget.SERVICE and payment.user_svc_id:
            usvc = await self.s.get(UserServicesModel, payment.user_svc_id)
            if usvc is not None:
                service = await self.s.get(ServiceModel, usvc.service_id)
                acc = await self.s.get(UserModel, payment.account_id)
                if service is not None and acc is not None:
                    await UserServicesMngr(self.s, self.bus, self.box).revoke(
                        usvc, service, acc
                    )
        else:  # возврат пополнения баланса
            acc = await self.s.get(UserModel, payment.account_id)
            if acc is not None:
                # Списываем не больше суммы этого платежа и не больше того,
                # что реально ещё есть на балансе — старые/чужие средства
                # не трогаем и в минус не уходим.
                deduct = min(acc.balance, payment.amount)
                acc.balance -= deduct
                shortfall = payment.amount - deduct
                payment.private_data = {
                    **(payment.private_data or {}),
                    "refund": {
                        "deducted": str(deduct),
                        "shortfall": str(shortfall),
                    },
                }
                if shortfall > 0:
                    # Часть суммы уже потрачена — списать в минус не можем,
                    # оставляем след для ручного разбора саппортом.
                    await audit(
                        self.s,
                        action="payment_refund_shortfall",
                        target_type="payment",
                        target_id=payment.id,
                        result="warn",
                        meta={
                            "amount": str(payment.amount),
                            "deducted": str(deduct),
                            "shortfall": str(shortfall),
                            "account_id": payment.account_id,
                        },
                    )

        await self.s.flush()
        if self.dispatcher is not None:
            await self.dispatcher.fire(
                TriggerEvent.PAYMENT_REFUNDED,
                {
                    "payment": {
                        "id": payment.id,
                        "account_id": payment.account_id,
                        "amount": str(payment.amount),
                        "target": payment.target,
                    }
                },
            )

    async def _locate(
        self, priv: dict, provider_slug: str, *, for_update: bool = False
    ) -> UserPaymentsModel | None:
        """Найти платёж по payment_id или external_id из ответа скрипта."""
        pid = priv.get("payment_id")
        if pid is not None:
            try:
                return await self.s.get(
                    UserPaymentsModel, int(pid), with_for_update=for_update
                )
            except (TypeError, ValueError):
                return None
        ext = priv.get("external_id")
        if ext:
            stmt = select(UserPaymentsModel).where(
                UserPaymentsModel.provider == provider_slug,
                UserPaymentsModel.external_id == str(ext),
            )
            if for_update:
                stmt = stmt.with_for_update()
            return await self.s.scalar(stmt)
        return None

    async def _settle(self, payment: UserPaymentsModel, priv: dict) -> None:
        """Провести успешный платёж: баланс или выдача оплаченной услуги."""
        payment.status = PayStatus.PAID
        payment.paid_at = utc_now()
        if priv.get("external_id"):
            payment.external_id = str(priv["external_id"])

        acc = await self.s.get(UserModel, payment.account_id)

        if payment.target == PayTarget.SERVICE and payment.user_svc_id:
            usvc = await self.s.get(UserServicesModel, payment.user_svc_id)
            if usvc is not None:
                service = await self.s.get(ServiceModel, usvc.service_id)
                usvc.payment_id = payment.id
                await UserServicesMngr(self.s, self.bus, self.box).deliver(
                    usvc, service, acc
                )
        else:  # пополнение баланса
            acc.balance += payment.amount


def _blank_account() -> UserModel:
    """Заглушка аккаунта для контекста вебхука (реальный платёж ищем по ответу)."""
    return UserModel(
        id=0,
        login="",
        email=None,
        balance=Decimal("0"),
        bonus_balance=Decimal("0"),
    )


def _blank_payment(provider_slug: str) -> UserPaymentsModel:
    """Пустой платёж-заглушка для контекста вебхука."""
    return UserPaymentsModel(
        id=0,
        account_id=0,
        provider=provider_slug,
        amount=Decimal("0"),
        currency="RUB",
        status=PayStatus.PENDING,
        target=PayTarget.BALANCE,
        public_data={},
        private_data={},
    )


async def get_pay_mngr(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    dispatcher: TriggerDispatcher = Depends(get_dispatcher),
    bus: LuaBus = Depends(get_lua_bus_configured),
) -> PayMngr:
    cfg = request.app.state.settings
    return PayMngr(session, bus, make_secbox(cfg), dispatcher)


def get_pay_providers_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> PaymentProvidersMngr:
    return PaymentProvidersMngr(session)


__all__ = ["PayMngr", "get_pay_mngr", "get_pay_providers_mngr"]
