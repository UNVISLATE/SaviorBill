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
from models.app_tokens import AppTokensMngr, hash_app_token
from utils.datetime_utils import utc_now
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
    headers = getattr(request, "headers", None)
    app_token_header = headers.get("X-App-Token") if headers is not None else None
    cookies = getattr(request, "cookies", {}) or {}
    token = cred.credentials if cred is not None else (app_token_header or cookies.get(ACCESS_COOKIE))
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer required")

    if token.startswith("sbapp_live_") or token.startswith("sb_app_live_"):
        token_hash = hash_app_token(token)
        session = getattr(mngr, "s", None)
        if session is not None:
            app_tokens_mngr = AppTokensMngr(session)
            app_token = await app_tokens_mngr.by_hash(token_hash)
            if not app_token or app_token.is_revoked:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked app token")
            if app_token.expires_at and app_token.expires_at < utc_now():
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "app token expired")

            client = getattr(request, "client", None)
            client_ip = client.host if client else "unknown"
            if not app_token.check_ip_allowed(client_ip):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "ip not allowed for this app token")

            await app_tokens_mngr.touch(app_token.id, client_ip)
            await session.commit()
            request_state = getattr(request, "state", None)
            if request_state is not None:
                request_state.app_token = app_token

            if app_token.creator:
                return app_token.creator
            return UserModel(
                id=app_token.created_by_account_id or 0,
                login=f"app:{app_token.name}",
                role_id=None,
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked app token")
    cfg = _cfg(request)
    try:
        claims = jwtu.decode_jwt(
            token, cfg.jwt_public_keys(), cfg.JWT_ALG, cfg.JWT_ISS
        )
    except jwtu.InvalidJWT as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    if claims.typ != jwtu.ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access_token expected")
    request_state = getattr(request, "state", None)
    if request_state is not None:
        request_state.auth_session_id = claims.extra.get("sid")

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
