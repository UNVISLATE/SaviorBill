from __future__ import annotations

import httpx
import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.sec import get_secbox
from dependencies.valkey import get_valkey_client
from integrations.oauth import OAuthRT, get_provider
from models.oauth_providers import OAuthProvidersModel
from models.user import UserModel
from models.user_oauth import UserOauthModel
from schemas.oauth import OAuthStart, OIDCUser
from utils.config import AppConfig
from utils.sec.box import SecBox
from utils.sec.crypt import generate_base_token

# Ключ state в Valkey и его TTL (антифрод/CSRF на время редиректа).
_STATE = "oauth:state:"
_STATE_TTL = 600


class OAuthSvc:
    """Высокоуровневые операции OAuth-флоу поверх таблицы ``oauth_providers``."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        cfg: AppConfig,
        box: SecBox,
    ) -> None:
        self.s = session
        self.vk = vk
        self.cfg = cfg
        self.box = box

    def redirect_uri(self, slug: str) -> str:
        base = self.cfg.PUBLIC_URL.rstrip("/")
        return f"{base}/api/v1/callback/oauth/{slug}"

    async def _cfg(self, slug: str) -> OAuthProvidersModel:
        row = await self.s.scalar(
            select(OAuthProvidersModel).where(
                OAuthProvidersModel.slug == slug,
                OAuthProvidersModel.enabled.is_(True),
            )
        )
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"провайдер {slug} недоступен"
            )
        return row

    def _runtime(self, cfg: OAuthProvidersModel) -> OAuthRT:
        return OAuthRT(
            slug=cfg.slug,
            client_id=cfg.client_id,
            client_secret=self.box.open(cfg.client_secret_enc),
            scopes=cfg.scopes,
            issuer=cfg.issuer,
            authorize_url=cfg.authorize_url,
            token_url=cfg.token_url,
            userinfo_url=cfg.userinfo_url,
            jwks_uri=cfg.jwks_uri,
            extra=cfg.extra or {},
        )

    async def start(self, slug: str) -> OAuthStart:
        """Подготовить редирект на провайдера: discovery + state."""
        cfg = await self._cfg(slug)
        prov = get_provider(slug)(self._runtime(cfg))
        async with httpx.AsyncClient(timeout=15) as client:
            await prov.discover(client)

        state = generate_base_token()
        await self.vk.set(_STATE + state, slug, ex=_STATE_TTL)
        return OAuthStart(
            authorize_url=prov.auth_url(state, self.redirect_uri(slug)),
            state=state,
        )

    async def finish(self, slug: str, code: str, state: str) -> OIDCUser:
        """Проверить state, обменять код и вернуть нормализованный профиль."""
        saved = await self.vk.get(_STATE + state)
        if saved != slug:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший state"
            )
        await self.vk.delete(_STATE + state)

        cfg = await self._cfg(slug)
        prov = get_provider(slug)(self._runtime(cfg))
        async with httpx.AsyncClient(timeout=15) as client:
            await prov.discover(client)
            tokens = await prov.exchange(client, code, self.redirect_uri(slug))
            return await prov.userinfo(client, tokens)

    async def link_account(self, slug: str, user: OIDCUser) -> UserModel:
        """Найти/создать аккаунт по внешней учётке и обновить привязку."""
        conn = await self.s.scalar(
            select(UserOauthModel).where(
                UserOauthModel.provider == slug, UserOauthModel.subject == user.sub
            )
        )
        if conn is not None:
            conn.email = user.email
            conn.raw = user.raw
            acc = await self.s.get(UserModel, conn.account_id)
            if acc is None:  # осиротевшая привязка — пересоздадим аккаунт ниже
                conn = None

        if conn is None:
            acc = None
            # Связываем с существующим аккаунтом только при подтверждённом email.
            if user.email and user.email_verified:
                acc = await self.s.scalar(
                    select(UserModel).where(UserModel.email == user.email)
                )
            if acc is None:
                acc = UserModel(
                    login=f"{slug}:{user.sub}"[:64],
                    email=user.email,
                    is_verified=user.email_verified,
                )
                self.s.add(acc)
                await self.s.flush()
            self.s.add(
                UserOauthModel(
                    account_id=acc.id,
                    provider=slug,
                    subject=user.sub,
                    email=user.email,
                    raw=user.raw,
                )
            )

        await self.s.flush()
        return acc


def get_oauth_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    box: SecBox = Depends(get_secbox),
) -> OAuthSvc:
    return OAuthSvc(session, vk, request.app.state.settings, box)


__all__ = ["OAuthSvc", "get_secbox", "get_oauth_svc"]
