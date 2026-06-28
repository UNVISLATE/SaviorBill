"""Роли и иерархические права доступа (RBAC)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from orm.mixins import PkMixin, TsMixin

if TYPE_CHECKING:
    from models.user import Account


class Role(PkMixin, TsMixin, Base):
    """Роль с древовидными правами.

    ``perms`` — вложенный словарь вида ``{"payment": {"refund": true}}``.
    Доступ к узлу даёт доступ ко всем его подпунктам (см. DEV.md, RBAC).
    """

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Системные роли нельзя удалять из админки.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    perms: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    accounts: Mapped[list["Account"]] = relationship(back_populates="role")


__all__ = ["Role"]
