"""Выдача услуг пользователю: списание, доставка (ключ или Lua), возврат."""

from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.lua import get_lua_bus
from enums import Delivery, OrderStatus, ScriptKind
from models.digikey import DigiKey
from models.luadb import LuaScript
from models.service import Service
from models.user import Account
from models.user_svc import UserSvc
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus


class UserSvcMngr:
    """Оформление выдачи услуги и её доставка (ключ или Lua-скрипт)."""

    def __init__(self, session: AsyncSession, bus: LuaBus) -> None:
        self.s = session
        self.bus = bus

    # --- деньги -----------------------------------------------------------
    @staticmethod
    def _charge(acc: Account, amount: Decimal) -> None:
        """Списать сумму: сначала бонусы, затем основной баланс."""
        if amount <= 0:
            return
        if acc.bonus_balance + acc.balance < amount:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED, "недостаточно средств"
            )
        from_bonus = min(acc.bonus_balance, amount)
        acc.bonus_balance -= from_bonus
        acc.balance -= amount - from_bonus

    @staticmethod
    def _refund(acc: Account, amount: Decimal) -> None:
        if amount > 0:
            acc.balance += amount

    # --- сценарии ---------------------------------------------------------
    async def create(
        self,
        acc: Account,
        service: Service,
        params: dict | None = None,
        discount: Decimal = Decimal("0"),
        *,
        charge: bool = True,
        deliver: bool = True,
        payment_id: int | None = None,
    ) -> UserSvc:
        """Создать выдачу.

        ``charge`` — списать стоимость с баланса (для оплаты с баланса).
        ``deliver`` — сразу выполнить доставку (False — отложить до оплаты
        платежом, см. :class:`PayMngr`). ``payment_id`` — привязка к платежу.
        """
        discount = max(Decimal("0"), min(discount, service.price))
        price = service.price - discount

        if charge:
            self._charge(acc, price)

        merged = dict(service.params or {})
        if params:
            merged.update(params)

        usvc = UserSvc(
            account_id=acc.id,
            service_id=service.id,
            payment_id=payment_id,
            status=OrderStatus.INITIATED,
            price=price,
            discount=discount,
            params=merged,
        )
        self.s.add(usvc)
        await self.s.flush()

        if deliver:
            await self.deliver(
                usvc, service, acc, refund_on_fail=price if charge else Decimal("0")
            )

        return usvc

    async def deliver(
        self,
        usvc: UserSvc,
        service: Service,
        acc: Account,
        *,
        refund_on_fail: Decimal = Decimal("0"),
    ) -> UserSvc:
        """Выполнить доставку услуги (ключ или Lua). Идемпотентна по статусу."""
        if usvc.status == OrderStatus.DELIVERED:
            return usvc
        try:
            if service.delivery == Delivery.KEY:
                await self._deliver_key(usvc, service)
            else:
                await self._deliver_lua(usvc, service, acc)
            usvc.status = OrderStatus.DELIVERED
            usvc.delivered_at = utc_now()
            usvc.error = None
        except Exception as exc:  # noqa: BLE001 — любая ошибка доставки -> возврат
            usvc.status = OrderStatus.FAILED
            usvc.error = str(exc)[:512]
            if refund_on_fail:
                self._refund(acc, refund_on_fail)
        await self.s.flush()
        return usvc

    async def _deliver_key(self, usvc: UserSvc, service: Service) -> None:
        """Выдать цифровой ключ из пула услуги."""
        key = await self.s.scalar(
            select(DigiKey)
            .where(DigiKey.service_id == service.id, DigiKey.is_used.is_(False))
            .order_by(DigiKey.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if key is None:
            raise RuntimeError("нет доступных ключей для услуги")
        key.is_used = True
        key.order_id = usvc.id
        key.used_at = utc_now()
        usvc.digikey_id = key.id
        usvc.public_data = {"key": key.value}
        usvc.private_data = {"digikey_id": key.id}

    async def _deliver_lua(self, usvc: UserSvc, service: Service, acc: Account) -> None:
        """Выдать услугу через Lua-скрипт (run_script).

        Контракт ctx:
          * ``user.*``         — пользователь, в т.ч. ``user.service`` (созданная
            услуга пользователя) и ``user.payment`` (id платежа или ``nil``);
          * ``service.*``      — эталонная услуга, в т.ч. ``service.settings.*``.
        """
        if not service.lua_script_id:
            raise RuntimeError("у услуги не задан Lua-скрипт")
        script = await self.s.get(LuaScript, service.lua_script_id)
        if script is None or not script.is_active or script.kind != ScriptKind.SERVICE:
            raise RuntimeError("Lua-скрипт услуги недоступен")

        ctx = {
            "user": {
                "id": acc.id,
                "login": acc.login,
                "email": acc.email,
                "service": {
                    "id": usvc.id,
                    "status": usvc.status,
                    "price": str(usvc.price),
                    "params": usvc.params,
                },
                "payment": usvc.payment_id,
            },
            "service": {
                "id": service.id,
                "slug": service.slug,
                "name": service.name,
                "price": str(service.price),
                "params": service.params,
                "settings": service.settings,
            },
        }
        res = await self.bus.call("run_script", {"script": script.filename, "ctx": ctx})
        usvc.public_data = res.get("public") or {}
        usvc.private_data = res.get("private") or {}


def get_usersvc_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> UserSvcMngr:
    return UserSvcMngr(session, get_lua_bus(request))


__all__ = ["UserSvcMngr", "get_usersvc_mngr"]
