"""Схемы OAuth-провайдеров (админ, Request/Response).

Провайдер работает через Lua-скрипт (``script_id``); креды/endpoints хранятся в
зашифрованном ``secrets`` (JSON) и прокидываются в скрипт как ``provider.secrets``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OAuthProvider(BaseModel):
    """OAuth-провайдер в админке (ответ, без секретов)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    script_id: int | None = None
    scopes: str
    extra: dict

    @classmethod
    def from_model(cls, m) -> "OAuthProvider":  # noqa: ANN001 — OAuthProvidersModel
        """Явное преобразование ORM-провайдера в схему ответа (без секретов)."""
        return cls.model_validate(m)


class OAuthProviderCreate(BaseModel):
    """Создание OAuth-провайдера.

    - `slug`: уникальный идентификатор провайдера (обязательно)
    - `script_id`: id auth-скрипта (start/callback) — обязателен для работы
    - `secrets`: секреты/endpoints провайдера, шифруются (опционально)
    - `title`: отображаемое имя (опционально)
    - `enabled`: включён ли провайдер (опционально)
    - `scopes`: запрашиваемые scope (опционально)
    - `extra`: несекретные доп-параметры для скрипта (опционально)
    """

    slug: str = Field(
        min_length=2,
        max_length=32,
        description="Уникальный slug провайдера (обязательно)",
    )
    script_id: int = Field(description="ID auth-скрипта провайдера (обязательно)")
    secrets: dict = Field(
        default_factory=dict,
        description="Секреты/endpoints провайдера, шифруются (опционально)",
    )
    title: str | None = Field(
        default=None, description="Отображаемое имя (опционально)"
    )
    enabled: bool = Field(
        default=False, description="Включён ли провайдер (опционально)"
    )
    scopes: str = Field(
        default="openid email profile",
        description="Запрашиваемые scope (опционально)",
    )
    extra: dict = Field(default_factory=dict, description="Доп-параметры (опционально)")


class OAuthProviderPatch(BaseModel):
    """Изменение OAuth-провайдера (только переданные поля).

    - `script_id`: id auth-скрипта (опционально)
    - `secrets`: новые секреты, перешифровываются (опционально)
    - `title`/`enabled`/`scopes`/`extra`: опционально
    """

    title: str | None = Field(
        default=None, description="Отображаемое имя (опционально)"
    )
    enabled: bool | None = Field(
        default=None, description="Включён ли провайдер (опционально)"
    )
    script_id: int | None = Field(
        default=None, description="ID auth-скрипта провайдера (опционально)"
    )
    secrets: dict | None = Field(
        default=None,
        description="Секреты провайдера, перешифровываются (опционально)",
    )
    scopes: str | None = Field(
        default=None, description="Запрашиваемые scope (опционально)"
    )
    extra: dict | None = Field(default=None, description="Доп-параметры (опционально)")


__all__ = ["OAuthProvider", "OAuthProviderCreate", "OAuthProviderPatch"]
