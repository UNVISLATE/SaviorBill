"""Схемы токенов приложений (App Tokens)."""

from __future__ import annotations

from datetime import datetime
import ipaddress
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppToken(BaseModel):
    """Схема токена приложения (без секрета)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    token_prefix: str
    permissions: list[str] = Field(default_factory=list)
    ip_allowlist: list[str] | None = None
    created_by_account_id: int | None = None
    created_by_login: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    is_revoked: bool
    revoked_at: datetime | None = None


class AppTokenCreated(AppToken):
    """Схема ответа при создании токена: секрет возвращается СТРОГО ОДИН РАЗ."""

    secret_token: str = Field(
        description="Полный секретный токен (sbapp_live_{tag}_...). Сохраните его сейчас — он никогда не будет показан повторно."
    )


class AppTokenCreate(BaseModel):
    """Схема запроса на создание токена приложения."""

    name: str = Field(min_length=2, max_length=128, description="Название приложения / бота")
    description: str | None = Field(default=None, max_length=1000, description="Описание назначения токена")
    permissions: list[str] = Field(
        default_factory=list, description="Список разрешений Scoped RBAC (например, orders.read, services.keys.read)"
    )
    ip_allowlist: list[str] | None = Field(
        default=None, max_length=100, description="Белый список IP или CIDR-сетей (если пусто — доступ со всех IP)"
    )
    expires_at: datetime | None = Field(
        default=None, description="Дата истечения срока действия (NULL — бессрочный)"
    )

    @field_validator("ip_allowlist")
    @classmethod
    def _validate_ips(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for item in v:
                try:
                    ipaddress.ip_network(item.strip(), strict=False)
                except ValueError:
                    raise ValueError(f"Invalid IP address or CIDR network: {item!r}")
        return v


__all__ = ["AppToken", "AppTokenCreated", "AppTokenCreate"]
