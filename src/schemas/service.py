"""Схемы услуг каталога (Request/Response)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
    image: str | None = None
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "Service":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в публичную схему ответа."""
        return cls.model_validate(m)


class ServiceAdmin(Service):
    """Услуга с административными полями (ответ)."""

    lua_script_id: int | None = None
    params: dict
    settings: dict

    @classmethod
    def from_model(cls, m) -> "ServiceAdmin":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в админ-схему ответа."""
        return cls.model_validate(m)


class ServiceCreate(BaseModel):
    """Создание услуги (админ)."""

    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="RUB", max_length=8)
    delivery: str = Field(default="key", description="key | lua")
    lua_script_id: int | None = None
    params: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)
    image: str | None = None
    is_active: bool = True


class ServicePatch(BaseModel):
    """Частичное изменение услуги (только переданные поля)."""

    name: str | None = None
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal | None = None
    currency: str | None = None
    delivery: str | None = None
    lua_script_id: int | None = None
    params: dict | None = None
    settings: dict | None = None
    image: str | None = None
    is_active: bool | None = None


__all__ = [
    "Service",
    "ServiceAdmin",
    "ServiceCreate",
    "ServicePatch",
]
