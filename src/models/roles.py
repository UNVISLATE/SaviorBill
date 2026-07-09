"""Роли и иерархические права доступа (RBAC)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from utils.datetime_utils import utc_now

if TYPE_CHECKING:
    from models.user import UserModel


class Role(Base):
    """Роль с древовидными правами.

    ``perms`` — вложенный словарь вида ``{"payment": {"refund": true}}``.
    Доступ к узлу даёт доступ ко всем его подпунктам (см. DEV.md, RBAC).
    """

    __tablename__ = "roles"

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

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Стабильный ключ базовой роли (owner/admin/user/guest/banned…), см. BaseRole.
    # NULL — пользовательская (не системная) роль. Не зависит от переименования.
    key: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    # Системные роли нельзя удалять из админки.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    perms: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )

    accounts: Mapped[list["UserModel"]] = relationship(back_populates="role")


__all__ = ["Role"]
