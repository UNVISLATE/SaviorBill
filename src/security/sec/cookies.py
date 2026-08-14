"""httpOnly auth-cookie: выставление/очистка access и refresh токенов.

Cookie — основной канал авторизации браузерного клиента (adminui): токены
недоступны JS (``httponly``), поэтому XSS не может украсть их из
``document.cookie``/``localStorage`` для долгоживущего захвата сессии (см.
AUDIT.md §6.1). ``Authorization: Bearer`` остаётся рабочим путём для
не-браузерных клиентов (скрипты, mediaworker-to-billing и т.п.) —
``dependencies/auth.py::get_current_acc`` принимает оба варианта.

Имена cookie должны совпадать между billing и mediaworker (см.
``mediaworker/src/utils/authctx.py``) — общий корневой домен
(``AppConfig.cookie_domain``) делает cookie видимой обоим сервисам.
"""

from __future__ import annotations

from fastapi import Response

from core.config import AppConfig

ACCESS_COOKIE = "sb_access"
REFRESH_COOKIE = "sb_refresh"


def set_auth_cookies(
    response: Response,
    cfg: AppConfig,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    """Выставить обе auth-cookie на ответ (login/register/refresh)."""
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=cfg.ACCESS_TOKEN_TTL,
        httponly=True,
        secure=not cfg.DEBUG,
        samesite="strict",
        domain=cfg.cookie_domain,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=cfg.REFRESH_TOKEN_TTL,
        httponly=True,
        secure=not cfg.DEBUG,
        samesite="strict",
        domain=cfg.cookie_domain,
        # Refresh-токен нужен только для /auth/refresh и /auth/logout —
        # уже суженный path не даёт ему уходить с каждым обычным запросом.
        path="/api/v1/auth",
    )


def clear_auth_cookies(response: Response, cfg: AppConfig) -> None:
    """Снять обе auth-cookie (logout)."""
    response.delete_cookie(
        ACCESS_COOKIE, domain=cfg.cookie_domain, path="/", samesite="strict"
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        domain=cfg.cookie_domain,
        path="/api/v1/auth",
        samesite="strict",
    )


__all__ = ["ACCESS_COOKIE", "REFRESH_COOKIE", "set_auth_cookies", "clear_auth_cookies"]
