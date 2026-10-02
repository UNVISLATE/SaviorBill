from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.banned_email_domains import BannedEmailDomainsMngr
from models.user import UserModel, UserMngr
from services.auth import TokenSvc
from core.config import AppConfig
from security.sec import jwt as jwtu
from security.sec.cookies import ACCESS_COOKIE

_bearer = HTTPBearer(auto_error=False)


def _cfg(request: Request) -> AppConfig:
    return request.app.state.settings


def get_acc_mngr(session: AsyncSession = Depends(get_db_session)) -> UserMngr:
    return UserMngr(session)


def get_banned_domains_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> BannedEmailDomainsMngr:
    return BannedEmailDomainsMngr(session)


def get_token_svc(
    request: Request,
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
) -> TokenSvc:
    return TokenSvc(_cfg(request), vk, settings, session)


async def get_current_acc(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    mngr: UserMngr = Depends(get_acc_mngr),
) -> UserModel:
    """Достать аккаунт из access-токена.

    Источник токена: ``Authorization: Bearer`` (не-браузерные клиенты) либо,
    если заголовка нет, httpOnly cookie ``sb_access`` (adminui, см.
    ``security/sec/cookies.py``) — заголовок в приоритете, если передан.
    """
    token = cred.credentials if cred is not None else request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer required")
    cfg = _cfg(request)
    try:
        claims = jwtu.decode_jwt(
            token, cfg.jwt_public_keys(), cfg.JWT_ALG, cfg.JWT_ISS
        )
    except jwtu.InvalidJWT as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    if claims.typ != jwtu.ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access_token expected")

    acc = await mngr.by_id(int(claims.sub))
    if acc is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")
    # Доступ к конкретным действиям решает исключительно RBAC (require_perm/
    # has_perm) на правах текущей роли — banned не хардкодится тут отдельно:
    # это просто роль, которую назначают при бане, без своих прав по
    # умолчанию. Если её правам явно дать конкретный perm — он будет работать.
    return acc


async def get_current_acc_optional(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    mngr: UserMngr = Depends(get_acc_mngr),
) -> UserModel | None:
    """Как :func:`get_current_acc`, но ``None`` без токена/при невалидном токене.

    Для публичных роутов, у которых поведение опционально меняется для
    залогиненного пользователя (например, превью скидки промокода — без
    аккаунта нельзя проверить лимиты "на пользователя", но код всё равно
    можно предпоказать по его собственным правилам каталога).
    """
    try:
        return await get_current_acc(request, cred, mngr)
    except HTTPException:
        return None


__all__ = [
    "UserModel",
    "UserMngr",
    "TokenSvc",
    "get_acc_mngr",
    "get_banned_domains_mngr",
    "get_token_svc",
    "get_current_acc",
    "get_current_acc_optional",
]
