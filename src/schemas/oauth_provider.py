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
    """OAuth provider."""

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
    """Create OAuth provider."""

    slug: str = Field(
        min_length=2,
        max_length=32,
        description="Unique provider slug",
    )
    script_id: int = Field(description="Auth script ID")
    secrets: dict = Field(
        default_factory=dict,
        description="Provider secrets/endpoints (optional)",
    )
    title: str | None = Field(
        default=None, description="Display name (optional)"
    )
    enabled: bool = Field(
        default=False, description="Enabled (optional)"
    )
    icon_media_id: int | None = Field(
        default=None, description="Provider icon media ID (optional)"
    )
    scopes: str = Field(
        default="openid email profile",
        description="Requested scopes (optional)",
    )
    extra: dict = Field(default_factory=dict, description="Extra params (optional)")


class OAuthProviderPatch(BaseModel):
    """Update OAuth provider."""

    title: str | None = Field(
        default=None, description="Display name (optional)"
    )
    enabled: bool | None = Field(
        default=None, description="Enabled (optional)"
    )
    script_id: int | None = Field(
        default=None, description="Auth script ID (optional)"
    )
    secrets: dict | None = Field(
        default=None,
        description="Provider secrets (optional)",
    )
    icon_media_id: int | None = Field(
        default=None,
        description="Provider icon media ID; null removes icon",
    )
    scopes: str | None = Field(
        default=None, description="Requested scopes (optional)"
    )
    extra: dict | None = Field(default=None, description="Extra params (optional)")


__all__ = ["OAuthProvider", "OAuthProviderCreate", "OAuthProviderPatch"]
