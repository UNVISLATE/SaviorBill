"""Контракты OAuth слоя (Python <-> провайдеры через Lua)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Provider(BaseModel):
    """Enabled provider for frontend."""

    slug: str
    title: str | None = None
    icon_url: str | None = None


class OAuthStart(BaseModel):
    """OAuth start response."""

    authorize_url: str
    state: str


class OAuthUser(BaseModel):
    """Normalized provider user."""

    model_config = ConfigDict(extra="ignore")

    sub: str = Field(description="Provider user ID")
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None
    raw: dict = Field(default_factory=dict)


class TokenSet(BaseModel):
    """Provider token set."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str | None = None
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None


class Conn(BaseModel):
    """External account link."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    subject: str
    email: str | None = None

    @classmethod
    def from_model(cls, m) -> "Conn":  # noqa: ANN001 — UserOauthModel
        """Явное преобразование ORM-привязки в схему.

        :arg m: модель привязки.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class OAuthPendingLink(BaseModel):
    """Response when the OAuth login matches an existing account by email but
    is not yet confirmed as belonging to the same person (see
    ``OAuthSvc.link_account``)."""

    pending: bool = True
    pending_token: str
    message: str = (
        "A confirmation code was sent to the existing account's email. "
        "Confirm via POST /api/v1/callback/oauth/pending/{pending_token}/confirm."
    )


class OAuthPendingConfirm(BaseModel):
    """Body to confirm a pending OAuth link."""

    code: str = Field(description="Confirmation code sent to the existing account's email")


__all__ = [
    "Provider",
    "OAuthStart",
    "OAuthUser",
    "TokenSet",
    "Conn",
    "OAuthPendingLink",
    "OAuthPendingConfirm",
]
