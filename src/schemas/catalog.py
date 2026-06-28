"""Контракты каталога услуг, каталогов и Lua-скриптов."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ServiceOut(BaseModel):
    """Услуга в каталоге."""

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


class ServiceAdminOut(ServiceOut):
    """Услуга с административными полями."""

    lua_script_id: int | None = None
    params: dict
    settings: dict


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


class CatalogOut(BaseModel):
    """Каталог услуг."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None = None
    description: str | None = None
    icon: str | None = None
    sort: int
    is_active: bool


class CatalogIn(BaseModel):
    """Создание каталога (админ)."""

    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=2, max_length=64)
    parent_id: int | None = None
    description: str | None = Field(default=None, max_length=512)
    icon: str | None = None
    sort: int = 0
    is_active: bool = True


class CatalogPatch(BaseModel):
    """Частичное изменение каталога."""

    name: str | None = None
    parent_id: int | None = None
    description: str | None = None
    icon: str | None = None
    sort: int | None = None
    is_active: bool | None = None


class ScriptOut(BaseModel):
    """Зарегистрированный Lua-скрипт."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    filename: str
    is_active: bool


class ScriptIn(BaseModel):
    """Загрузка нового Lua-скрипта (код пишется в монтируемую папку)."""

    slug: str = Field(min_length=2, max_length=64)
    name: str | None = None
    kind: str = Field(default="service", description="service | payment | generic")
    filename: str = Field(
        description="Имя файла относительно LUA_SCRIPTS_DIR, напр. services/my.lua"
    )
    code: str = Field(description="Тело Lua-скрипта (модуль с функцией handle(ctx))")
    description: str | None = None


class ScriptPatch(BaseModel):
    """Изменение тела Lua-скрипта."""

    code: str = Field(description="Новое тело Lua-скрипта")


__all__ = [
    "ServiceOut",
    "ServiceAdminOut",
    "ServiceCreate",
    "ServicePatch",
    "CatalogOut",
    "CatalogIn",
    "CatalogPatch",
    "ScriptOut",
    "ScriptIn",
    "ScriptPatch",
]
