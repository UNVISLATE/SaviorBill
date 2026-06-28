"""GitHub — OAuth2 (не OIDC). Пример переопределения особенностей платформы."""

from __future__ import annotations

import httpx

from integrations.oauth.base import OIDCBase
from integrations.oauth.registry import reg
from schemas.oauth import OIDCUser, TokenSet


@reg("github")
class GitHub(OIDCBase):
    """GitHub не отдаёт id_token и userinfo по OIDC — ходим в REST API."""

    AUTHORIZE = "https://github.com/login/oauth/authorize"
    TOKEN = "https://github.com/login/oauth/access_token"
    API_USER = "https://api.github.com/user"
    API_EMAILS = "https://api.github.com/user/emails"

    def __init__(self, rt) -> None:  # type: ignore[no-untyped-def]
        super().__init__(rt)
        # У GitHub фиксированные эндпоинты и нет discovery.
        self.rt.authorize_url = self.rt.authorize_url or self.AUTHORIZE
        self.rt.token_url = self.rt.token_url or self.TOKEN
        if not self.rt.scopes or self.rt.scopes.startswith("openid"):
            self.rt.scopes = "read:user user:email"

    async def discover(self, client: httpx.AsyncClient) -> None:
        # discovery не нужен — эндпоинты заданы в __init__.
        return

    async def userinfo(self, client: httpx.AsyncClient, tokens: TokenSet) -> OIDCUser:
        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Accept": "application/vnd.github+json",
        }
        u = (await client.get(self.API_USER, headers=headers)).raise_for_status().json()

        email = u.get("email")
        verified = bool(email)
        if not email:
            # У приватных профилей основной email отдаётся отдельным запросом.
            emails = (
                (await client.get(self.API_EMAILS, headers=headers))
                .raise_for_status()
                .json()
            )
            primary = next(
                (e for e in emails if e.get("primary")), emails[0] if emails else {}
            )
            email = primary.get("email")
            verified = bool(primary.get("verified"))

        return OIDCUser(
            sub=str(u["id"]),
            email=email,
            email_verified=verified,
            name=u.get("name") or u.get("login"),
            picture=u.get("avatar_url"),
            raw=u,
        )
