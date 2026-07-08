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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from enums import Delivery, UsvcStatus
from models.service_catalogs import ServiceCatalogsModel
from models.system_scripts import SystemScriptsModel
from utils.datetime_utils import utc_now

# Статусы выданных услуг, которые считаются "активными" (не завершёнными) —
# для мягкого предупреждения при деактивации услуги с такими заказами.
_ACTIVE_USVC_STATUSES = (UsvcStatus.PENDING, UsvcStatus.ACTIVE, UsvcStatus.FROZEN)


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
        ForeignKey("lua_scripts.id", ondelete="RESTRICT"), nullable=True, index=True
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

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Вложения товара (фото/видео), см. ServiceAttachmentModel.
    attachments: Mapped[list["ServiceAttachmentModel"]] = relationship(  # noqa: F821
        "ServiceAttachmentModel",
        order_by="ServiceAttachmentModel.position, ServiceAttachmentModel.id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


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

    async def _validate_catalog(self, catalog_id: int | None) -> None:
        """404, если указанный каталог не существует."""
        if catalog_id is None:
            return
        if await self.s.get(ServiceCatalogsModel, catalog_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "каталог не найден")

    async def _validate_lua_script(
        self, delivery: str | None, lua_script_id: int | None
    ) -> None:
        """400, если для lua-доставки скрипт не задан/не найден/неактивен."""
        if delivery != Delivery.LUA:
            return
        if lua_script_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "для delivery=lua необходимо указать lua_script_id",
            )
        script = await self.s.get(SystemScriptsModel, lua_script_id)
        if script is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "lua_script_id: скрипт не найден"
            )
        if not script.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "lua_script_id: скрипт неактивен"
            )

    async def _active_orders_warning(self, service_id: int) -> list[str]:
        """Мягкое предупреждение: у услуги есть незавершённые выдачи.

        Не блокирует деактивацию (soft-warning, не 409) — по решению
        пользователя это некритичная ситуация.
        """
        from models.user_services import UserServicesModel  # разрыв цикла импорта

        count = await self.s.scalar(
            select(func.count())
            .select_from(UserServicesModel)
            .where(
                UserServicesModel.service_id == service_id,
                UserServicesModel.status.in_(_ACTIVE_USVC_STATUSES),
            )
        )
        if count:
            return [
                f"у услуги есть {count} незавершённых выдач(и) — "
                "они продолжат обслуживаться штатно, но новые заказы больше не создать"
            ]
        return []

    async def create(self, data: dict) -> ServiceModel:
        if await self.s.scalar(
            select(ServiceModel).where(ServiceModel.slug == data["slug"])
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug услуги занят")
        await self._validate_catalog(data.get("catalog_id"))
        await self._validate_lua_script(
            data.get("delivery", Delivery.KEY), data.get("lua_script_id")
        )
        svc = ServiceModel(**data)
        self.s.add(svc)
        await self.s.flush()
        return svc

    async def update(self, service_id: int, data: dict) -> tuple[ServiceModel, list[str]]:
        svc = await self.by_id(service_id)
        if svc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
        if "catalog_id" in data:
            await self._validate_catalog(data["catalog_id"])
        if "delivery" in data or "lua_script_id" in data:
            delivery = data.get("delivery", svc.delivery)
            lua_script_id = data.get("lua_script_id", svc.lua_script_id)
            await self._validate_lua_script(delivery, lua_script_id)

        warnings: list[str] = []
        if data.get("is_active") is False and svc.is_active:
            warnings = await self._active_orders_warning(service_id)

        for field, value in data.items():
            setattr(svc, field, value)
        await self.s.flush()
        return svc, warnings


__all__ = ["ServiceModel", "ServiceMngr"]
