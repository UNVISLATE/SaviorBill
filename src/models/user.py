"""Аккаунты пользователей (единая таблица под авторизацию)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from orm.mixins import PkMixin, TsMixin

if TYPE_CHECKING:
    from models.oauth_conn import OAuthConn
    from models.roles import Role


class Account(PkMixin, TsMixin, Base):
    """Учётная запись. Роль — через ``role_id`` (RBAC).

    ``pass_hash`` может быть ``NULL`` для аккаунтов, заведённых только через
    OAuth (вход по внешнему провайдеру, без локального пароля).
    """

    __tablename__ = "accounts"

    login: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    pass_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Денежные балансы (Decimal, никаких float). bonus тратится первым.
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    bonus_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    role: Mapped["Role | None"] = relationship(back_populates="accounts", lazy="joined")
    oauth_conns: Mapped[list["OAuthConn"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )

    @property
    def has_pass(self) -> bool:
        """Есть ли у аккаунта локальный пароль."""
        return self.pass_hash is not None


__all__ = ["Account"]
