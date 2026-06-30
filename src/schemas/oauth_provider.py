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


class OAuthProviderPatch(BaseModel):
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


__all__ = ["OAuthProvider", "OAuthProviderCreate", "OAuthProviderPatch"]
