"""Эталонная услуга каталога (ServiceModel) + менеджер (ServiceMngr)."""

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
    Select,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import Delivery
from utils.datetime_utils import utc_now


class ServiceModel(Base):
    """Услуга-объект каталога (эталон).

    ``delivery`` определяет способ выдачи:
      * ``key`` — из пула :class:`ServiceKeysModel`, привязанных к этой услуге;
      * ``lua`` — исполнением скрипта ``lua_script_id`` с передачей данных
        пользователя и ``settings`` услуги.

    ``settings`` — JSON эталонной услуги (прокидывается в Lua как
    ``service.settings.*``). Позволяет одним скриптом обслуживать несколько
    похожих услуг с разными параметрами (срок действия и т.п.).
    """

    __tablename__ = "services"

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

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Каталог (NULL — корневой товар, см. ServiceCatalogsModel).
    catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("svc_catalogs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)

    # key | lua (см. Delivery).
    delivery: Mapped[str] = mapped_column(
        String(8), default=Delivery.KEY, nullable=False
    )
    lua_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Кастом-параметры услуги (снимок прокидывается в скрипт как ctx.params).
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # JSON-настройки эталонной услуги (ctx.service.settings).
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Поддерживаемые действия ЖЦ (наследуются выданной услугой и отдаются фронту):
    # ["create","renew","stop","delete","freeze"] — см. ServiceAction.
    actions: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    # Срок действия услуги в секундах (NULL — бессрочная). Используется billing-loop
    # для планирования истечения, если lua-шаблон сам не вернул expires_at.
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Путь к изображению/иконке услуги в хранилище.
    image: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceMngr:
    """Доступ к каталогу услуг и их администрирование."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_active(self, catalog_id: int | None = None) -> list[ServiceModel]:
        rows = await self.s.scalars(self.stmt_active(catalog_id))
        return list(rows)

    def stmt_active(self, catalog_id: int | None = None) -> Select:
        """Базовый select активных услуг (для пагинации).

        :arg catalog_id: опциональный фильтр по каталогу.
        :return: select без limit/offset, упорядоченный по id.
        """
        stmt = select(ServiceModel).where(ServiceModel.is_active.is_(True))
        if catalog_id is not None:
            stmt = stmt.where(ServiceModel.catalog_id == catalog_id)
        return stmt.order_by(ServiceModel.id)

    async def list_all(self) -> list[ServiceModel]:
        rows = await self.s.scalars(self.stmt_all())
        return list(rows)

    def stmt_all(self) -> Select:
        """Базовый select всех услуг (для пагинации)."""
        return select(ServiceModel).order_by(ServiceModel.id)

    async def by_id(self, service_id: int) -> ServiceModel | None:
        return await self.s.get(ServiceModel, service_id)

    async def get_active(self, service_id: int) -> ServiceModel:
        svc = await self.by_id(service_id)
        if svc is None or not svc.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
        return svc

    async def create(self, data: dict) -> ServiceModel:
        if await self.s.scalar(
            select(ServiceModel).where(ServiceModel.slug == data["slug"])
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug услуги занят")
        svc = ServiceModel(**data)
        self.s.add(svc)
        await self.s.flush()
        return svc

    async def update(self, service_id: int, data: dict) -> ServiceModel:
        svc = await self.by_id(service_id)
        if svc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
        for field, value in data.items():
            setattr(svc, field, value)
        await self.s.flush()
        return svc


__all__ = ["ServiceModel", "ServiceMngr"]
