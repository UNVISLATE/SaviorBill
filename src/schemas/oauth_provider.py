"""Схемы OAuth-провайдеров (админ, Request/Response).

Провайдер работает через Lua-скрипт (``script_id``); креды/endpoints хранятся в
зашифрованном ``secrets`` (JSON) и прокидываются в скрипт как ``provider.secrets``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


def _icon_url(token: str | None) -> str | None:
    """Относительный URL иконки провайдера (см. ``schemas.media``)."""
    return f"/media/{token}" if token else None


class OAuthProvider(BaseModel):
    """OAuth-провайдер в админке (ответ, без секретов)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    script_id: int | None = None
    icon_media_id: int | None = None
    icon_url: str | None = None
    scopes: str
    extra: dict

    @classmethod
    def from_model(cls, m) -> "OAuthProvider":  # noqa: ANN001 — OAuthProvidersModel
        """Явное преобразование ORM-провайдера в схему ответа (без секретов)."""
        return cls(
            id=m.id,
            slug=m.slug,
            title=m.title,
            enabled=m.enabled,
            script_id=m.script_id,
            icon_media_id=m.icon_media_id,
            icon_url=_icon_url(m.icon.token if m.icon else None),
            scopes=m.scopes,
            extra=m.extra,
        )


class OAuthProviderCreate(BaseModel):
    """Создание OAuth-провайдера.

    - `slug`: уникальный идентификатор провайдера (обязательно)
    - `script_id`: id auth-скрипта (start/callback) — обязателен для работы
    - `secrets`: секреты/endpoints провайдера, шифруются (опционально)
    - `title`: отображаемое имя (опционально)
    - `enabled`: включён ли провайдер (опционально)
    - `icon_media_id`: ID медиа-иконки провайдера (опционально)
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
    icon_media_id: int | None = Field(
        default=None, description="ID медиа-иконки провайдера (опционально)"
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
    - `icon_media_id`: ID медиа-иконки, `null` — снять иконку (опционально)
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
    icon_media_id: int | None = Field(
        default=None,
        description="ID медиа-иконки провайдера; null — снять иконку (опционально)",
    )
    scopes: str | None = Field(
        default=None, description="Запрашиваемые scope (опционально)"
    )
    extra: dict | None = Field(default=None, description="Доп-параметры (опционально)")


__all__ = ["OAuthProvider", "OAuthProviderCreate", "OAuthProviderPatch"]
