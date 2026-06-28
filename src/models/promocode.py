"""Промокод: бонус на баланс, скидка на товар, выдача услуги."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import DiscountType
from orm.mixins import PkMixin, TsMixin


class Promocode(PkMixin, TsMixin, Base):
    """Промокод одного из типов (см. :class:`enums.PromoKind`).

    * ``bonus``    — ``value`` зачисляется на бонусный баланс;
    * ``discount`` — ``value`` + ``discount_type`` дают скидку при заказе;
    * ``service``  — по коду выдаётся услуга ``service_id``.
    """

    __tablename__ = "promocodes"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    # bonus: сумма; discount: размер скидки; service: не используется.
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    # percent | fixed (для discount).
    discount_type: Mapped[str] = mapped_column(
        String(8), default=DiscountType.PERCENT, nullable=False
    )
    # Для kind=service: какая услуга выдаётся.
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )

    # Лимиты использования.
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    per_user: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["Promocode"]
