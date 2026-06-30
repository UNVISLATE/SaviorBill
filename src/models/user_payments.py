"""Платёж пользователя (UserPaymentsModel) + менеджер (UserPaymentsMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import PayStatus, PayTarget
from utils.datetime_utils import utc_now


class UserPaymentsModel(Base):
    """Платёж

    Создаётся в статусе ``pending``; init-скрипт провайдера возвращает данные
    для редиректа (``public_data``). Подтверждение приходит колбэком и
    переводит платёж в ``paid``.

    ``target`` определяет назначение:
      * ``balance`` — зачисление на баланс аккаунта;
      * ``service`` — оплата конкретной выдачи (``user_svc_id``).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    public_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    private_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=PayStatus.PENDING, index=True, nullable=False
    )

    target: Mapped[str] = mapped_column(
        String(16), default=PayTarget.BALANCE, nullable=False
    )
    user_svc_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Идентификатор платежа на стороне провайдера.
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserPaymentsMngr:
    """Базовый data-access для платежей пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, payment_id: int) -> UserPaymentsModel | None:
        return await self.s.get(UserPaymentsModel, payment_id)

    async def by_external_id(
        self, provider: str, external_id: str
    ) -> UserPaymentsModel | None:
        return await self.s.scalar(
            select(UserPaymentsModel).where(
                UserPaymentsModel.provider == provider,
                UserPaymentsModel.external_id == external_id,
            )
        )

    async def list_for_account(
        self, account_id: int, limit: int = 50
    ) -> list[UserPaymentsModel]:
        rows = await self.s.scalars(
            select(UserPaymentsModel)
            .where(UserPaymentsModel.account_id == account_id)
            .order_by(UserPaymentsModel.id.desc())
            .limit(limit)
        )
        return list(rows)

    async def create(
        self,
        account_id: int,
        provider: str,
        amount: Decimal,
        *,
        currency: str = "RUB",
        target: str = PayTarget.BALANCE,
        user_svc_id: int | None = None,
    ) -> UserPaymentsModel:
        payment = UserPaymentsModel(
            account_id=account_id,
            provider=provider,
            amount=amount,
            currency=currency,
            target=target,
            user_svc_id=user_svc_id,
        )
        self.s.add(payment)
        await self.s.flush()
        return payment


__all__ = ["UserPaymentsModel", "UserPaymentsMngr"]
