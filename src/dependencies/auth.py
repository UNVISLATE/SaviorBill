from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.valkey import get_valkey_client
from models.user import UserModel, UserMngr
from services.auth import TokenSvc
from utils.config import AppConfig
from security.sec import jwt as jwtu

_bearer = HTTPBearer(auto_error=False)


def _cfg(request: Request) -> AppConfig:
    return request.app.state.settings


def get_acc_mngr(session: AsyncSession = Depends(get_db_session)) -> UserMngr:
    return UserMngr(session)


def get_token_svc(
    request: Request, vk: valkey.Valkey = Depends(get_valkey_client)
) -> TokenSvc:
    return TokenSvc(_cfg(request), vk)


async def get_current_acc(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    mngr: UserMngr = Depends(get_acc_mngr),
) -> UserModel:
    """Достать аккаунт из access-токена (Authorization: Bearer ...)."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer required")
    cfg = _cfg(request)
    try:
        claims = jwtu.decode_jwt(
            cred.credentials, cfg.JWT_SECRET, cfg.JWT_ALG, cfg.JWT_ISS
        )
    except jwtu.InvalidJWT as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    if claims.typ != jwtu.ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access_token expected")

    acc = await mngr.by_id(int(claims.sub))
    if acc is None or not acc.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")
    return acc


__all__ = [
    "UserModel",
    "UserMngr",
    "TokenSvc",
    "get_acc_mngr",
    "get_token_svc",
    "get_current_acc",
]
