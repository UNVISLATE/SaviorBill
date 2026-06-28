"""Базовый OIDC-провайдер и рантайм-конфиг.

Каждая платформа — отдельный скрипт в ``integrations/oauth/providers/``,
наследующий :class:`OIDCBase`. По умолчанию реализован «чистый» OIDC
(Authorization Code Flow + discovery + userinfo). Платформенные особенности
(GitHub, VK и т.п.) переопределяют нужные методы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from schemas.oauth import OIDCUser, TokenSet


@dataclass(slots=True)
class OAuthRT:
    """Рантайм-конфигурация провайдера (секрет уже расшифрован)."""

    slug: str
    client_id: str
    client_secret: str
    scopes: str = "openid email profile"
    issuer: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    jwks_uri: str | None = None
    extra: dict = field(default_factory=dict)


class OIDCBase:
    """Стандартный OIDC-провайдер. Наследуйте и переопределяйте по необходимости."""

    # Можно переопределить в наследнике, если у платформы фиксированный issuer.
    default_issuer: str | None = None

    def __init__(self, rt: OAuthRT) -> None:
        self.rt = rt
        if rt.issuer is None and self.default_issuer:
            self.rt.issuer = self.default_issuer

    # --- discovery -------------------------------------------------------
    async def discover(self, client: httpx.AsyncClient) -> None:
        """Догрузить эндпоинты через ``/.well-known/openid-configuration``."""
        if self.rt.authorize_url and self.rt.token_url:
            return
        if not self.rt.issuer:
            raise RuntimeError(f"{self.rt.slug}: не задан issuer и нет явных URL")
        url = self.rt.issuer.rstrip("/") + "/.well-known/openid-configuration"
        resp = await client.get(url)
        resp.raise_for_status()
        doc = resp.json()
        self.rt.authorize_url = self.rt.authorize_url or doc.get("authorization_endpoint")
        self.rt.token_url = self.rt.token_url or doc.get("token_endpoint")
        self.rt.userinfo_url = self.rt.userinfo_url or doc.get("userinfo_endpoint")
        self.rt.jwks_uri = self.rt.jwks_uri or doc.get("jwks_uri")

    # --- authorize -------------------------------------------------------
    def auth_url(self, state: str, redirect_uri: str) -> str:
        """Собрать URL, на который редиректится пользователь."""
        params = {
            "response_type": "code",
            "client_id": self.rt.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.rt.scopes,
            "state": state,
            **self.rt.extra.get("auth_params", {}),
        }
        return f"{self.rt.authorize_url}?{urlencode(params)}"

    # --- token exchange --------------------------------------------------
    async def exchange(
        self, client: httpx.AsyncClient, code: str, redirect_uri: str
    ) -> TokenSet:
        """Обменять authorization code на токены."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.rt.client_id,
            "client_secret": self.rt.client_secret,
        }
        resp = await client.post(
            self.rt.token_url, data=data, headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        return TokenSet.model_validate(resp.json())

    # --- userinfo --------------------------------------------------------
    async def userinfo(self, client: httpx.AsyncClient, tokens: TokenSet) -> OIDCUser:
        """Получить и нормализовать профиль пользователя."""
        if not self.rt.userinfo_url:
            raise RuntimeError(f"{self.rt.slug}: не задан userinfo_url")
        resp = await client.get(
            self.rt.userinfo_url,
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        resp.raise_for_status()
        return self.to_user(resp.json())

    def to_user(self, data: dict) -> OIDCUser:
        """Привести сырой ответ провайдера к :class:`OIDCUser`.

        Переопределите, если у платформы нестандартные имена полей.
        """
        return OIDCUser(
            sub=str(data["sub"]),
            email=data.get("email"),
            email_verified=bool(data.get("email_verified", False)),
            name=data.get("name"),
            picture=data.get("picture"),
            raw=data,
        )


__all__ = ["OAuthRT", "OIDCBase"]
