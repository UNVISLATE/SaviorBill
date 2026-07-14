"""Иерархический каталог услуг (ServiceCatalogsModel) + менеджер (ServiceCatalogsMngr)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class ServiceCatalogsModel(Base):
    """Каталог (или подкаталог) услуг.

    ``parent_id`` указывает на родительский каталог; ``NULL`` — корневой
    каталог. Услуга (``ServiceModel.catalog_id``) без каталога считается корневым
    товаром. Структура нужна исключительно для отображения в UI.
    """

    __tablename__ = "svc_catalogs"

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
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("svc_catalogs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceCatalogsMngr:
    """CRUD иерархических каталогов услуг."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_all(self) -> list[ServiceCatalogsModel]:
        rows = await self.s.scalars(
            select(ServiceCatalogsModel).order_by(
                ServiceCatalogsModel.sort, ServiceCatalogsModel.id
            )
        )
        return list(rows)

    async def by_id(self, catalog_id: int) -> ServiceCatalogsModel | None:
        return await self.s.get(ServiceCatalogsModel, catalog_id)

    async def create(self, data: dict) -> ServiceCatalogsModel:
        if await self.s.scalar(
            select(ServiceCatalogsModel).where(
                ServiceCatalogsModel.slug == data["slug"]
            )
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "catalog slug already taken")
        parent_id = data.get("parent_id")
        if parent_id is not None and await self.by_id(parent_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "parent catalog not found")
        cat = ServiceCatalogsModel(**data)
        self.s.add(cat)
        await self.s.flush()
        return cat

    async def update(self, catalog_id: int, data: dict) -> ServiceCatalogsModel:
        cat = await self.by_id(catalog_id)
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog not found")
        if data.get("parent_id") == catalog_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "catalog cannot be its own parent"
            )
        for field, value in data.items():
            setattr(cat, field, value)
        await self.s.flush()
        return cat

    async def delete(self, catalog_id: int) -> None:
        cat = await self.by_id(catalog_id)
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog not found")
        await self.s.delete(cat)
        await self.s.flush()


__all__ = ["ServiceCatalogsModel", "ServiceCatalogsMngr"]
