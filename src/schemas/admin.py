"""Контракты административного API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    """Аккаунт в админ-списке."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role_id: int | None = None
    balance: Decimal
    bonus_balance: Decimal
    created_at: datetime
    last_login: datetime | None = None


class UserPatch(BaseModel):
    """Частичное редактирование аккаунта (только переданные поля)."""

    email: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role_id: int | None = None
    balance: Decimal | None = None
    bonus_balance: Decimal | None = None


class RoleOut(BaseModel):
    """Роль с деревом прав."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str | None = None
    is_system: bool
    perms: dict


class RoleIn(BaseModel):
    """Создание роли."""

    name: str = Field(min_length=2, max_length=64)
    title: str | None = None
    perms: dict = Field(default_factory=dict)


class RolePatch(BaseModel):
    """Изменение роли."""

    title: str | None = None
    perms: dict | None = None


class PermsCatalog(BaseModel):
    """Каталог прав для назначения ролям."""

    flat: list[str]
    tree: dict


class PayProviderOut(BaseModel):
    """Платёжный провайдер (без секретов)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    currency: str
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict


class PayProviderIn(BaseModel):
    """Создание платёжного провайдера."""

    slug: str = Field(min_length=2, max_length=64)
    title: str | None = None
    enabled: bool = False
    currency: str = Field(default="RUB", max_length=8)
    # JSON секретов/доп-данных платёжки (шифруется при сохранении).
    secrets: dict = Field(default_factory=dict)
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict = Field(default_factory=dict)


class PayProviderPatch(BaseModel):
    """Изменение платёжного провайдера (только переданные поля)."""

    title: str | None = None
    enabled: bool | None = None
    currency: str | None = None
    secrets: dict | None = None
    init_script_id: int | None = None
    cb_script_id: int | None = None
    extra: dict | None = None


class OAuthCfgOut(BaseModel):
    """OAuth-провайдер в админке (без client_secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    client_id: str
    issuer: str | None = None
    scopes: str
    extra: dict


class OAuthCfgIn(BaseModel):
    """Создание OAuth-провайдера."""

    slug: str = Field(min_length=2, max_length=32)
    title: str | None = None
    enabled: bool = False
    client_id: str
    client_secret: str
    issuer: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    jwks_uri: str | None = None
    scopes: str = "openid email profile"
    extra: dict = Field(default_factory=dict)


class OAuthCfgPatch(BaseModel):
    """Изменение OAuth-провайдера (только переданные поля)."""

    title: str | None = None
    enabled: bool | None = None
    client_id: str | None = None
    client_secret: str | None = None
    issuer: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    jwks_uri: str | None = None
    scopes: str | None = None
    extra: dict | None = None


__all__ = [
    "UserOut",
    "UserPatch",
    "RoleOut",
    "RoleIn",
    "RolePatch",
    "PermsCatalog",
    "PayProviderOut",
    "PayProviderIn",
    "PayProviderPatch",
    "OAuthCfgOut",
    "OAuthCfgIn",
    "OAuthCfgPatch",
]
