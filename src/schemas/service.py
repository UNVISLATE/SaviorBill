"""Схемы услуг каталога (Request/Response)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from schemas.media import Attachment


class Service(BaseModel):
    """Услуга в публичном каталоге (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal
    currency: str
    delivery: str
    attachments: list[Attachment] = Field(
        default_factory=list, description="Медиа-вложения товара (фото/видео)"
    )
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "Service":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в публичную схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            catalog_id=m.catalog_id,
            price=m.price,
            currency=m.currency,
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
        )


class ServiceAdmin(Service):
    """Услуга с административными полями (ответ)."""

    lua_script_id: int | None = None
    params: dict
    settings: dict

    @classmethod
    def from_model(cls, m) -> "ServiceAdmin":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в админ-схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            catalog_id=m.catalog_id,
            price=m.price,
            currency=m.currency,
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
            lua_script_id=m.lua_script_id,
            params=m.params,
            settings=m.settings,
        )


class ServiceCreate(BaseModel):
    """Создание услуги (админ)."""

    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug услуги (обязательно)"
    )
    name: str = Field(
        min_length=1, max_length=128, description="Название услуги (обязательно)"
    )
    description: str | None = Field(default=None, description="Описание (опционально)")
    catalog_id: int | None = Field(
        default=None, description="ID каталога; null — корневая (опционально)"
    )
    price: Decimal = Field(
        default=Decimal("0"), ge=0, description="Цена ≥ 0 (опционально)"
    )
    currency: str = Field(
        default="RUB", max_length=8, description="Валюта (опционально)"
    )
    delivery: str = Field(
        default="key", description="Способ выдачи: key | lua (опционально)"
    )
    lua_script_id: int | None = Field(
        default=None, description="ID lua-скрипта для delivery=lua (опционально)"
    )
    params: dict = Field(
        default_factory=dict, description="Параметры выдачи (опционально)"
    )
    settings: dict = Field(
        default_factory=dict, description="Настройки услуги (опционально)"
    )
    is_active: bool = Field(default=True, description="Активна ли услуга (опционально)")


class ServicePatch(BaseModel):
    """Частичное изменение услуги (только переданные поля)."""

    name: str | None = Field(default=None, description="Название услуги")
    description: str | None = Field(default=None, description="Описание")
    catalog_id: int | None = Field(default=None, description="ID каталога")
    price: Decimal | None = Field(default=None, description="Цена")
    currency: str | None = Field(default=None, description="Валюта")
    delivery: str | None = Field(default=None, description="Способ выдачи: key | lua")
    lua_script_id: int | None = Field(default=None, description="ID lua-скрипта")
    params: dict | None = Field(default=None, description="Параметры выдачи")
    settings: dict | None = Field(default=None, description="Настройки услуги")
    is_active: bool | None = Field(default=None, description="Активна ли услуга")


__all__ = [
    "Service",
    "ServiceAdmin",
    "ServiceCreate",
    "ServicePatch",
]
