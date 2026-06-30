"""Каталоги промокодов (PromoCatalogsModel) + менеджер (PromoCatalogsMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from enums import DiscountType, PromoKind
from models import Base
from utils.datetime_utils import utc_now


class PromoCatalogsModel(Base):
    """Каталог промокодов — описывает, ЧТО делает активация кода.

    Сам промокод (:class:`models.promo_codes.PromoCodesModel`) хранит только
    символы, лимит и срок. Поведение (бонус/скидка/услуга) задаётся здесь, что
    позволяет выпускать пачки кодов с единым действием.
    """

    __tablename__ = "promo_catalogs"

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

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("promo_catalogs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Поведение активации.
    kind: Mapped[str] = mapped_column(
        String(16), default=PromoKind.BONUS, nullable=False
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    discount_type: Mapped[str] = mapped_column(
        String(8), default=DiscountType.PERCENT, nullable=False
    )
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    # Сколько раз один пользователь может активировать код из этого каталога.
    per_user: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )

    # Произвольные настройки/условия активации.
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PromoCatalogsMngr:
    """CRUD для каталогов промокодов."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, catalog_id: int) -> PromoCatalogsModel | None:
        """Найти каталог по id.

        :arg catalog_id: идентификатор каталога.
        :return: каталог или ``None``.
        """
        return await self.s.get(PromoCatalogsModel, catalog_id)

    async def by_slug(self, slug: str) -> PromoCatalogsModel | None:
        """Найти каталог по slug.

        :arg slug: уникальный slug каталога.
        :return: каталог или ``None``.
        """
        return await self.s.scalar(
            select(PromoCatalogsModel).where(PromoCatalogsModel.slug == slug)
        )

    async def list_all(self) -> list[PromoCatalogsModel]:
        """Все каталоги по порядку id.

        :return: список каталогов.
        """
        rows = await self.s.scalars(
            select(PromoCatalogsModel).order_by(PromoCatalogsModel.id)
        )
        return list(rows)

    async def create(self, data: dict) -> PromoCatalogsModel:
        """Создать каталог промокодов.

        :arg data: поля каталога (name, slug, kind, value, ...).
        :return: созданный каталог.
        """
        catalog = PromoCatalogsModel(**data)
        self.s.add(catalog)
        await self.s.flush()
        return catalog

    async def update(self, catalog_id: int, data: dict) -> PromoCatalogsModel | None:
        """Обновить переданные поля каталога.

        :arg catalog_id: идентификатор каталога.
        :arg data: изменяемые поля.
        :return: обновлённый каталог или ``None``.
        """
        cat = await self.by_id(catalog_id)
        if cat is None:
            return None
        for field, val in data.items():
            setattr(cat, field, val)
        await self.s.flush()
        return cat

    async def delete(self, catalog_id: int) -> None:
        """Удалить каталог (его коды удаляются каскадно).

        :arg catalog_id: идентификатор каталога.
        """
        cat = await self.by_id(catalog_id)
        if cat is not None:
            await self.s.delete(cat)
            await self.s.flush()


__all__ = ["PromoCatalogsModel", "PromoCatalogsMngr"]
