"""DI и сервисы авторизации: текущий аккаунт, AccMngr, TokenSvc."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.valkey import get_valkey_client
from models.user import Account
from schemas.auth import TokenPair
from utils.config import AppConfig
from utils.datetime_utils import timestamp_now, utc_now
from utils.sec import jwt as jwtu

_bearer = HTTPBearer(auto_error=False)

# Префикс ключей денлиста отозванных refresh-jti в Valkey.
_DENY = "auth:deny:"


def _cfg(request: Request) -> AppConfig:
    return request.app.state.settings


class AccMngr:
    """Менеджер аккаунтов (тонкий слой доступа к данным)."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, acc_id: int) -> Account | None:
        return await self.s.get(Account, acc_id)

    async def by_login(self, login: str) -> Account | None:
        return await self.s.scalar(select(Account).where(Account.login == login))

    async def by_email(self, email: str) -> Account | None:
        return await self.s.scalar(select(Account).where(Account.email == email))

    async def create(
        self, login: str, pass_hash: str | None, email: str | None = None
    ) -> Account:
        acc = Account(login=login, pass_hash=pass_hash, email=email)
        self.s.add(acc)
        await self.s.flush()
        return acc

    async def touch_login(self, acc: Account) -> None:
        """Обновить отметку последнего входа."""
        acc.last_login = utc_now()
        await self.s.flush()


class TokenSvc:
    """Выпуск/ротация/отзыв JWT с денлистом refresh в Valkey."""

    def __init__(self, cfg: AppConfig, vk: valkey.Valkey) -> None:
        self.cfg = cfg
        self.vk = vk

    def _access(self, acc: Account) -> str:
        return jwtu.make_access(
            str(acc.id),
            self.cfg.JWT_SECRET,
            self.cfg.JWT_ALG,
            self.cfg.ACCESS_TTL,
            self.cfg.JWT_ISS,
            extra={"login": acc.login, "role": acc.role.name if acc.role else None},
        )

    def _refresh(self, acc: Account) -> str:
        return jwtu.make_refresh(
            str(acc.id),
            self.cfg.JWT_SECRET,
            self.cfg.JWT_ALG,
            self.cfg.REFRESH_TTL,
            self.cfg.JWT_ISS,
        )

    def issue(self, acc: Account) -> TokenPair:
        """Выпустить новую пару токенов."""
        return TokenPair(
            access_token=self._access(acc),
            refresh_token=self._refresh(acc),
            expires_in=self.cfg.ACCESS_TTL,
        )

    def _decode_refresh(self, token: str) -> jwtu.Claims:
        claims = jwtu.decode_jwt(
            token, self.cfg.JWT_SECRET, self.cfg.JWT_ALG, self.cfg.JWT_ISS
        )
        if claims.typ != jwtu.REFRESH:
            raise jwtu.BadToken("ожидался refresh-токен")
        return claims

    async def revoke(self, claims: jwtu.Claims) -> None:
        """Занести refresh-jti в денлист до его естественного истечения."""
        ttl = max(claims.exp - timestamp_now(), 1)
        await self.vk.set(_DENY + claims.jti, "1", ex=ttl)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self.vk.exists(_DENY + jti))

    async def rotate(self, refresh_token: str, mngr: AccMngr) -> tuple[Account, TokenPair]:
        """Проверить refresh, отозвать старый, выдать новую пару."""
        try:
            claims = self._decode_refresh(refresh_token)
        except jwtu.BadToken as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
        if await self.is_revoked(claims.jti):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "токен отозван")

        acc = await mngr.by_id(int(claims.sub))
        if acc is None or not acc.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "аккаунт недоступен")

        await self.revoke(claims)  # ротация: старый refresh больше не валиден
        return acc, self.issue(acc)


# --- FastAPI dependencies -----------------------------------------------


def get_acc_mngr(session: AsyncSession = Depends(get_db_session)) -> AccMngr:
    return AccMngr(session)


def get_token_svc(
    request: Request, vk: valkey.Valkey = Depends(get_valkey_client)
) -> TokenSvc:
    return TokenSvc(_cfg(request), vk)


async def get_current_acc(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    mngr: AccMngr = Depends(get_acc_mngr),
) -> Account:
    """Достать аккаунт из access-токена (Authorization: Bearer ...)."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "нужен Bearer-токен")
    cfg = _cfg(request)
    try:
        claims = jwtu.decode_jwt(
            cred.credentials, cfg.JWT_SECRET, cfg.JWT_ALG, cfg.JWT_ISS
        )
    except jwtu.BadToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    if claims.typ != jwtu.ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "нужен access-токен")

    acc = await mngr.by_id(int(claims.sub))
    if acc is None or not acc.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "аккаунт недоступен")
    return acc


__all__ = [
    "AccMngr",
    "TokenSvc",
    "get_acc_mngr",
    "get_token_svc",
    "get_current_acc",
]
