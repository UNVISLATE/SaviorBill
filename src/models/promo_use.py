"""Факт применения промокода (аудит и лимиты per-user)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import PkMixin, TsMixin


class PromoUse(PkMixin, TsMixin, Base):
    """Факт применения промокода (аудит и лимиты per-user)."""

    __tablename__ = "promo_uses"

    promocode_id: Mapped[int] = mapped_column(
        ForeignKey("promocodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


__all__ = ["PromoUse"]
