"""Иерархический каталог услуг (для UI-группировки товаров)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from orm.mixins import PkMixin, TsMixin


class SvcCatalog(PkMixin, TsMixin, Base):
    """Каталог (или подкаталог) услуг.

    ``parent_id`` указывает на родительский каталог; ``NULL`` — корневой
    каталог. Услуга (``Service.catalog_id``) без каталога считается корневым
    товаром. Структура нужна исключительно для отображения в UI.
    """

    __tablename__ = "svc_catalogs"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("svc_catalogs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Путь к иконке каталога в хранилище (StorageSvc).
    icon: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["SvcCatalog"]
