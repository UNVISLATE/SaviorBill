"""Платёжные провайдеры (PaymentProvidersModel) + менеджер (PaymentProvidersMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    func,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class PaymentProvidersModel(Base):
    """Запись о платёжном провайдере (ЮKassa, Stripe, …).

    ``secrets_enc`` — зашифрованный (SecBox) JSON с секретами и уникальными
    данными платёжки (ключи API, shop_id, webhook-секрет и т.п.). В рантайме
    он расшифровывается и прокидывается в Lua-скрипты провайдера.

    Каждая платёжка работает по-своему, поэтому у провайдера один action-driven
    Lua-скрипт (``script_id``), который обрабатывает все действия платежа:
    ``create`` (инициализация, вернуть ссылку), ``callback`` (доверенный вебхук),
    ``check`` (перепроверка у API) и ``refund`` (возврат). Обязательны create и
    callback — см. :class:`enums.PayAction`.
    """

    __tablename__ = "pay_providers"

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

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Зашифрованный JSON секретов/доп-данных платёжки.
    secrets_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)

    # Единый action-driven скрипт провайдера (create/callback/check/refund).
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Несекретные дополнительные настройки провайдера.
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class PaymentProvidersMngr:
    """CRUD для платёжных провайдеров."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, provider_id: int) -> PaymentProvidersModel | None:
        return await self.s.get(PaymentProvidersModel, provider_id)

    async def by_slug(
        self, slug: str, *, enabled_only: bool = False
    ) -> PaymentProvidersModel | None:
        stmt = select(PaymentProvidersModel).where(PaymentProvidersModel.slug == slug)
        if enabled_only:
            stmt = stmt.where(PaymentProvidersModel.enabled.is_(True))
        return await self.s.scalar(stmt)

    async def list_all(self) -> list[PaymentProvidersModel]:
        rows = await self.s.scalars(
            select(PaymentProvidersModel).order_by(PaymentProvidersModel.id)
        )
        return list(rows)

    async def list_enabled(self) -> list[PaymentProvidersModel]:
        rows = await self.s.scalars(
            select(PaymentProvidersModel)
            .where(PaymentProvidersModel.enabled.is_(True))
            .order_by(PaymentProvidersModel.id)
        )
        return list(rows)

    async def create(self, **data) -> PaymentProvidersModel:
        provider = PaymentProvidersModel(**data)
        self.s.add(provider)
        await self.s.flush()
        return provider


__all__ = ["PaymentProvidersModel", "PaymentProvidersMngr"]
