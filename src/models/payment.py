"""Платёж: денежная транзакция через платёжного провайдера."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import PayStatus, PayTarget
from orm.mixins import JsonDataMixin, PkMixin, TsMixin


class Payment(PkMixin, TsMixin, JsonDataMixin, Base):
    """Платёж (бывш. ``Topup``).

    Создаётся в статусе ``pending``; init-скрипт провайдера возвращает данные
    для редиректа (``public_data``). Подтверждение приходит колбэком и
    переводит платёж в ``paid``.

    ``target`` определяет назначение:
      * ``balance`` — зачисление на баланс аккаунта;
      * ``service`` — оплата конкретной выдачи (``user_svc_id``).
    """

    __tablename__ = "payments"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # slug провайдера (PayProvider.slug).
    provider: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=PayStatus.PENDING, index=True, nullable=False
    )

    # balance | service (см. PayTarget).
    target: Mapped[str] = mapped_column(
        String(16), default=PayTarget.BALANCE, nullable=False
    )
    # Если target=service: какую выдачу оплачивает платёж (без FK — циклическая связь).
    user_svc_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Идентификатор платежа на стороне провайдера.
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["Payment"]
