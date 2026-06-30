"""Схемы OAuth-провайдеров (админ, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OAuthProvider(BaseModel):
    """OAuth-провайдер в админке (ответ, без client_secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    client_id: str
    issuer: str | None = None
    scopes: str
    extra: dict

    @classmethod
    def from_model(cls, m) -> "OAuthProvider":  # noqa: ANN001 — OAuthProvidersModel
        """Явное преобразование ORM-провайдера в схему ответа (без секрета)."""
        return cls.model_validate(m)


class OAuthProviderCreate(BaseModel):
    """Создание OAuth-провайдера."""

    slug: str = Field(
        min_length=2,
        max_length=32,
        description="Уникальный slug провайдера (обязательно)",
    )
    title: str | None = Field(
        default=None, description="Отображаемое имя (опционально)"
    )
    enabled: bool = Field(
        default=False, description="Включён ли провайдер (опционально)"
    )
    client_id: str = Field(description="OAuth client_id (обязательно)")
    client_secret: str = Field(
        description="OAuth client_secret, шифруется (обязательно)"
    )
    issuer: str | None = Field(
        default=None, description="Issuer для OIDC-автодискавери (опционально)"
    )
    authorize_url: str | None = Field(
        default=None, description="URL авторизации (опционально)"
    )
    token_url: str | None = Field(
        default=None, description="URL обмена кода на токен (опционально)"
    )
    userinfo_url: str | None = Field(
        default=None, description="URL получения профиля (опционально)"
    )
    jwks_uri: str | None = Field(
        default=None, description="JWKS URI для проверки id_token (опционально)"
    )
    scopes: str = Field(
        default="openid email profile", description="Запрашиваемые scope (опционально)"
    )
    extra: dict = Field(default_factory=dict, description="Доп-параметры (опционально)")


class OAuthProviderPatch(BaseModel):
    """Изменение OAuth-провайдера (только переданные поля)."""

    title: str | None = Field(default=None, description="Отображаемое имя")
    enabled: bool | None = Field(default=None, description="Включён ли провайдер")
    client_id: str | None = Field(default=None, description="OAuth client_id")
    client_secret: str | None = Field(
        default=None, description="OAuth client_secret (перешифровывается)"
    )
    issuer: str | None = Field(default=None, description="Issuer для OIDC")
    authorize_url: str | None = Field(default=None, description="URL авторизации")
    token_url: str | None = Field(default=None, description="URL обмена кода на токен")
    userinfo_url: str | None = Field(default=None, description="URL получения профиля")
    jwks_uri: str | None = Field(default=None, description="JWKS URI")
    scopes: str | None = Field(default=None, description="Запрашиваемые scope")
    extra: dict | None = Field(default=None, description="Доп-параметры")


__all__ = ["OAuthProvider", "OAuthProviderCreate", "OAuthProviderPatch"]
