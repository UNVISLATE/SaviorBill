"""Платежи через провайдеров: инициализация и обработка колбэка."""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.lua import get_lua_bus
from dependencies.sec import make_secbox
from dependencies.usersvc import UserServicesMngr
from enums import PayDirective, PayStatus, PayTarget
from models.payment_providers import PaymentProvidersModel, PaymentProvidersMngr
from models.service import ServiceModel
from models.system_scripts import SystemScriptsModel
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus
from utils.sec.box import SecBox


class PayMngr:
    """Создание платежей и обработка колбэков через скрипты провайдера."""

    def __init__(self, session: AsyncSession, bus: LuaBus, box: SecBox) -> None:
        self.s = session
        self.bus = bus
        self.box = box

    # --- доступ к провайдеру/секретам ------------------------------------
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

    async def _script(self, script_id: int | None, role: str) -> SystemScriptsModel:
        if not script_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"у провайдера не задан {role}-скрипт"
            )
        script = await self.s.get(SystemScriptsModel, script_id)
        if script is None or not script.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"{role}-скрипт провайдера недоступен"
            )
        return script

    def _prov_ctx(self, prov: PaymentProvidersModel) -> dict:
        return {
            "slug": prov.slug,
            "settings": self._secrets(prov),
            "extra": prov.extra or {},
        }

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
        """Создать платёж и запустить init-скрипт провайдера за ссылкой оплаты."""
        prov = await self._provider(provider_slug)
        script = await self._script(prov.init_script_id, "init")

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

        ctx = {
            "payment": {
                "id": payment.id,
                "amount": str(amount),
                "currency": payment.currency,
                "target": target,
                "user_svc_id": user_svc_id,
                "return_url": return_url,
            },
            "provider": self._prov_ctx(prov),
            "user": {"id": acc.id, "login": acc.login, "email": acc.email},
        }
        try:
            res = await self.bus.call(
                "run_script", {"script": script.filename, "ctx": ctx}
            )
            payment.public_data = res.get("public") or {}
            payment.private_data = res.get("private") or {}
            payment.external_id = (res.get("private") or {}).get("external_id")
        except Exception as exc:  # noqa: BLE001
            payment.status = PayStatus.FAILED
            payment.private_data = {"error": str(exc)[:512]}

        await self.s.flush()
        return payment

    # --- обработка колбэка -------------------------------------------------
    async def _run_cb(
        self, prov: PaymentProvidersModel, request_data: dict, directive: str
    ) -> tuple[dict, dict]:
        """Запустить callback-скрипт провайдера. Возвращает (result, private).

        :arg prov: провайдер.
        :arg request_data: данные запроса (вебхук) или сверки (recheck).
        :arg directive: PayDirective.WEBHOOK | RECHECK — режим для скрипта.
        """
        script = await self._script(prov.cb_script_id, "callback")
        ctx = {
            "provider": self._prov_ctx(prov),
            "request": request_data,
            "directive": directive,
        }
        res = await self.bus.call("run_script", {"script": script.filename, "ctx": ctx})
        return res, (res.get("private") or {})

    async def callback(
        self, provider_slug: str, request_data: dict
    ) -> UserPaymentsModel:
        """Обработать входящий вебхук провайдера (доверенный сервер-сервер).

        Скрипт сам проверяет подпись/ключ и возвращает результат в ``private``;
        мы полагаемся на его ответ без самостоятельной перепроверки.

        :arg provider_slug: slug провайдера из пути колбэка.
        :arg request_data: данные вебхука (тело + query).
        :return: обновлённый платёж.
        """
        prov = await self._provider(provider_slug)
        res, priv = await self._run_cb(prov, request_data, PayDirective.WEBHOOK)

        if not priv.get("ok"):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "колбэк не прошёл проверку"
            )

        payment = await self._locate(priv, provider_slug)
        if payment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "платёж не найден")
        if payment.status == PayStatus.PAID:
            return payment  # идемпотентность

        if priv.get("paid"):
            await self._settle(payment, priv)
        else:
            payment.status = PayStatus.FAILED

        # Сохраняем данные колбэка (для аудита).
        if res.get("public"):
            payment.public_data = {**(payment.public_data or {}), **res["public"]}
        payment.private_data = {**(payment.private_data or {}), **priv}

        await self.s.flush()
        return payment

    async def recheck(self, payment: UserPaymentsModel) -> UserPaymentsModel:
        """Перепроверить статус платежа у провайдера (директива ``recheck``).

        В отличие от вебхука, инициируем сверку сами: callback-скрипт по
        ``directive=recheck`` обращается к API провайдера. Успех → ``_settle``;
        отказ провайдера → ``failed``; неопределённость → платёж остаётся
        ``pending`` (планировщик решит, когда переводить в ``wait``).

        :arg payment: платёж для перепроверки.
        :return: обновлённый платёж.
        """
        if payment.status in (PayStatus.PAID, PayStatus.FAILED):
            return payment
        prov = await self._provider(payment.provider, enabled=False)
        request_data = {
            "payment_id": payment.id,
            "external_id": payment.external_id,
        }
        res, priv = await self._run_cb(prov, request_data, PayDirective.RECHECK)

        if priv.get("ok") and priv.get("paid"):
            await self._settle(payment, priv)
        elif priv.get("ok") and priv.get("failed"):
            payment.status = PayStatus.FAILED

        if res.get("public"):
            payment.public_data = {**(payment.public_data or {}), **res["public"]}
        payment.private_data = {**(payment.private_data or {}), **priv}
        await self.s.flush()
        return payment

    async def _locate(self, priv: dict, provider_slug: str) -> UserPaymentsModel | None:
        """Найти платёж по payment_id или external_id из ответа скрипта."""
        pid = priv.get("payment_id")
        if pid is not None:
            try:
                return await self.s.get(UserPaymentsModel, int(pid))
            except (TypeError, ValueError):
                return None
        ext = priv.get("external_id")
        if ext:
            return await self.s.scalar(
                select(UserPaymentsModel).where(
                    UserPaymentsModel.provider == provider_slug,
                    UserPaymentsModel.external_id == str(ext),
                )
            )
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
                await UserServicesMngr(self.s, self.bus).deliver(usvc, service, acc)
        else:  # пополнение баланса
            acc.balance += payment.amount


def get_pay_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> PayMngr:
    cfg = request.app.state.settings
    return PayMngr(session, get_lua_bus(request), make_secbox(cfg))


def get_pay_providers_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> PaymentProvidersMngr:
    return PaymentProvidersMngr(session)


__all__ = ["PayMngr", "get_pay_mngr", "get_pay_providers_mngr"]
