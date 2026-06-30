"""Контракты OAuth/OIDC слоя (Python <-> провайдеры)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Provider(BaseModel):
    """Краткая инфа о включённом провайдере для фронта."""

    slug: str
    title: str | None = None


class OAuthStart(BaseModel):
    """Ответ на старт авторизации: куда редиректить пользователя."""

    authorize_url: str
    state: str


class OIDCUser(BaseModel):
    """Нормализованный профиль пользователя от провайдера.

    Любая платформа обязана привести свой ответ к этому контракту
    (см. integrations/oauth/base.py). ``raw`` — исходные данные.
    """

    model_config = ConfigDict(extra="ignore")

    sub: str = Field(description="Идентификатор пользователя у провайдера")
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None
    raw: dict = Field(default_factory=dict)


class TokenSet(BaseModel):
    """Токены, выданные провайдером на этапе обмена кода."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str | None = None
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None


class Conn(BaseModel):
    """Привязка внешней учётки к аккаунту (для /user/oauth)."""

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


__all__ = ["Provider", "OAuthStart", "OIDCUser", "TokenSet", "Conn"]
