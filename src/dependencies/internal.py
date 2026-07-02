"""Гард служебного токена для внутреннего API (/internal).

Внутренние роуты вызывают доверенные сервисы (mediaworker, luaworker) в приватной
сети, авторизуясь общим сервисным токеном (``LUA_SERVICE_TOKEN``) в заголовке
``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.config import AppConfig

_bearer = HTTPBearer(auto_error=False)


async def require_service_token(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Проверить сервисный токен вызывающего сервиса.

    :raises HTTPException: токен не настроен или не совпал (401).
    """
    cfg: AppConfig = request.app.state.settings
    expected = cfg.LUA_SERVICE_TOKEN
    if not expected:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "service token not configured"
        )
    if cred is None or not secrets.compare_digest(cred.credentials, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "service token required")


__all__ = ["require_service_token"]
