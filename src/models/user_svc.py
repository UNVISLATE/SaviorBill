"""Выданная пользователю услуга (товар пользователя)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from enums import OrderStatus
from orm.mixins import JsonDataMixin, PkMixin, TsMixin
from models.service import Service


class UserSvc(PkMixin, TsMixin, JsonDataMixin, Base):
    """Экземпляр выданной услуги (бывш. ``Order``).

    Создаётся со статусом ``initiated``. После успешной доставки (ключ или
    Lua) переходит в ``delivered``; результат раскладывается на ``public_data``
    (отдаётся клиенту) и ``private_data`` (только система).

    ``payment_id`` — опциональная привязка к платежу, по которому выдана
    услуга. ``NULL`` — ручная выдача администратором (без оплаты).
    """

    __tablename__ = "user_services"

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

    service: Mapped["Service"] = relationship(lazy="joined")


__all__ = ["UserSvc"]
