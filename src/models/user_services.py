"""Выданная пользователю услуга (UserServicesModel) + менеджер (UserServicesMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import (
    func,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from enums import OrderStatus, UsvcState
from integrations.services import get_issuer
from utils.datetime_utils import utc_now
from utils.luabus import LuaBus


class UserServicesModel(Base):
    """Экземпляр выданной услуги (бывш. ``Order``).

    Создаётся со статусом ``initiated``. После успешной доставки (ключ или
    Lua) переходит в ``delivered``; результат раскладывается на ``public_data``
    (отдаётся клиенту) и ``private_data`` (только система).

    ``payment_id`` — опциональная привязка к платежу, по которому выдана
    услуга. ``NULL`` — ручная выдача администратором (без оплаты).
    """

    __tablename__ = "user_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    public_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    private_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Платёж, по которому выдана услуга (без FK — циклическая связь с payments).
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(16), default=OrderStatus.INITIATED, index=True, nullable=False
    )
    # Состояние ЖЦ выданной услуги (active/frozen/stopped/expired), см. UsvcState.
    state: Mapped[str] = mapped_column(
        String(16),
        default=UsvcState.ACTIVE,
        server_default=UsvcState.ACTIVE,
        index=True,
        nullable=False,
    )
    # Момент истечения услуги (для billing-loop). NULL — бессрочная.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Длительность в секундах на момент выдачи (снимок service.duration).
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Снимок поддерживаемых действий услуги (для фронтенда).
    actions: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    discount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )

    # Снимок кастом-параметров на момент заказа.
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Ключ из пула (без FK — циклическая связь с digi_keys).
    digikey_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    service: Mapped["ServiceModel"] = relationship(lazy="joined")


from models.service import ServiceModel


class UserServicesMngr:
    """Оформление выдачи услуги и её доставка (ключ или Lua-скрипт)."""

    def __init__(self, session: AsyncSession, bus: LuaBus) -> None:
        self.s = session
        self.bus = bus

    # --- деньги -----------------------------------------------------------
    @staticmethod
    def _charge(acc, amount: Decimal) -> None:
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
    def _refund(acc, amount: Decimal) -> None:
        if amount > 0:
            acc.balance += amount

    # --- сценарии ---------------------------------------------------------
    async def create(
        self,
        acc,
        service: ServiceModel,
        params: dict | None = None,
        discount: Decimal = Decimal("0"),
        *,
        charge: bool = True,
        deliver: bool = True,
        payment_id: int | None = None,
    ) -> UserServicesModel:
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

        usvc = UserServicesModel(
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
        usvc: UserServicesModel,
        service: ServiceModel,
        acc,
        *,
        refund_on_fail: Decimal = Decimal("0"),
    ) -> UserServicesModel:
        """Выполнить доставку услуги (ключ или Lua). Идемпотентна по статусу.

        Конкретный способ берётся из реестра нативных интеграций
        (:func:`integrations.services.get_issuer`).
        """
        if usvc.status == OrderStatus.DELIVERED:
            return usvc
        try:
            issuer = get_issuer(service.delivery, self.s, self.bus)
            await issuer.issue(usvc, service, acc)
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


__all__ = ["UserServicesModel", "UserServicesMngr"]
