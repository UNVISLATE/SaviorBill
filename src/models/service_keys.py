"""Пул цифровых ключей услуги (ServiceKeysModel) + менеджер (ServiceKeysMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class ServiceKeysModel(Base):
    """Цифровые ключи для выдачи, если услуга - цифровой ключ"""

    __tablename__ = "digi_keys"

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

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ServiceKeysMngr:
    """CRUD для цифровых ключей услуг."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, key_id: int) -> ServiceKeysModel | None:
        return await self.s.get(ServiceKeysModel, key_id)

    async def list_for_service(self, service_id: int) -> list[ServiceKeysModel]:
        rows = await self.s.scalars(
            select(ServiceKeysModel)
            .where(ServiceKeysModel.service_id == service_id)
            .order_by(ServiceKeysModel.id)
        )
        return list(rows)

    async def list_available(self, service_id: int) -> list[ServiceKeysModel]:
        rows = await self.s.scalars(
            select(ServiceKeysModel)
            .where(
                ServiceKeysModel.service_id == service_id,
                ServiceKeysModel.is_used.is_(False),
            )
            .order_by(ServiceKeysModel.id)
        )
        return list(rows)

    async def create(self, service_id: int, value: str) -> ServiceKeysModel:
        key = ServiceKeysModel(service_id=service_id, value=value)
        self.s.add(key)
        await self.s.flush()
        return key


__all__ = ["ServiceKeysModel", "ServiceKeysMngr"]
