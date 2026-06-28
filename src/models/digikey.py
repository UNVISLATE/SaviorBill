"""Пул цифровых ключей услуги (для delivery=key)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import PkMixin, TsMixin


class DigiKey(PkMixin, TsMixin, Base):
    """Цифровой ключ из пула услуги (для delivery=key)."""

    __tablename__ = "digi_keys"

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    # Выдача (user_svc), которой выдан ключ (без FK — избегаем циклической связи).
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["DigiKey"]
