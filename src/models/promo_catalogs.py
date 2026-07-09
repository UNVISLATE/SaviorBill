"""Каталоги промокодов (PromoCatalogsModel) + менеджер (PromoCatalogsMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import (
    func,
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

from enums import PromoKind
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

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    # Поведение активации.
    kind: Mapped[str] = mapped_column(
        String(16), default=PromoKind.BONUS, nullable=False
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    # Осмыслен только при kind == discount; для остальных kind должен быть
    # NULL (см. PromoCatalogsMngr._validate_kind_discount — единственное
    # место, проверяющее это правило и на create, и на update).
    discount_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    # Лимит на количество РАЗНЫХ кодов этого каталога, которые может
    # погасить один пользователь. NULL — без лимита. Любое погашение кода
    # само по себе ограничено 1 разом на пользователя независимо от этого
    # поля (см. PromoCodesMngr.load_valid).
    per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Условия активации (зарезервировано на будущее, формат пока не задан
    # и не проверяется исполняемой логикой).
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
        self._validate_kind_discount(
            data.get("kind", PromoKind.BONUS), data.get("discount_type")
        )
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
        # Валидация — по итоговому состоянию (текущее значение + патч), а
        # не по частично переданным полям: например, PATCH только с
        # discount_type должен учитывать уже сохранённый kind, и наоборот.
        kind = data.get("kind", cat.kind)
        discount_type = data.get("discount_type", cat.discount_type)
        self._validate_kind_discount(kind, discount_type)
        for field, val in data.items():
            setattr(cat, field, val)
        await self.s.flush()
        return cat

    @staticmethod
    def _validate_kind_discount(kind: str, discount_type: str | None) -> None:
        """Проверить согласованность ``kind`` и ``discount_type``.

        ``discount_type`` обязателен и осмыслен только при ``kind ==
        discount`` — для остальных видов каталога он не должен указываться
        вовсе (ни на уровне ввода, ни на уровне итогового состояния строки).

        :arg kind: тип действия каталога.
        :arg discount_type: тип скидки (``None`` — не задан).
        :raises HTTPException: если комбинация недопустима.
        """
        if kind == PromoKind.DISCOUNT:
            if discount_type is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "discount_type is required for kind=discount",
                )
        elif discount_type is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "discount_type is only allowed for kind=discount",
            )

    async def delete(self, catalog_id: int) -> None:
        """Удалить каталог (его коды удаляются каскадно).

        :arg catalog_id: идентификатор каталога.
        """
        cat = await self.by_id(catalog_id)
        if cat is not None:
            await self.s.delete(cat)
            await self.s.flush()


__all__ = ["PromoCatalogsModel", "PromoCatalogsMngr"]
