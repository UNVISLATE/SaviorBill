"""Эталонная услуга каталога."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import Delivery
from orm.mixins import PkMixin, TsMixin


class Service(PkMixin, TsMixin, Base):
    """Услуга-объект каталога (эталон).

    ``delivery`` определяет способ выдачи:
      * ``key`` — из пула :class:`DigiKey`, привязанных к этой услуге;
      * ``lua`` — исполнением скрипта ``lua_script_id`` с передачей данных
        пользователя и ``settings`` услуги.

    ``settings`` — JSON эталонной услуги (прокидывается в Lua как
    ``service.settings.*``). Позволяет одним скриптом обслуживать несколько
    похожих услуг с разными параметрами (срок действия и т.п.).
    """

    __tablename__ = "services"

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Каталог (NULL — корневой товар, см. SvcCatalog).
    catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("svc_catalogs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)

    # key | lua (см. Delivery).
    delivery: Mapped[str] = mapped_column(String(8), default=Delivery.KEY, nullable=False)
    lua_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Кастом-параметры услуги (снимок прокидывается в скрипт как ctx.params).
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # JSON-настройки эталонной услуги (ctx.service.settings).
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Путь к изображению/иконке услуги в хранилище.
    image: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["Service"]
