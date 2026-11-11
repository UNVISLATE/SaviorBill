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

from fastapi import Request, Response

from core.config import AppConfig

ACCESS_COOKIE = "sb_access"
REFRESH_COOKIE = "sb_refresh"


def _resolve_cookie_domain(
    cfg: AppConfig, request: Request | None = None
) -> str | None:
    """Выбрать ``Domain`` для auth-cookie с учётом отдельного ``CLIENT_DOMAIN``.

    Для ``DOMAIN``/``MEDIA_DOMAIN`` возвращается общий корневой ``cfg.cookie_domain``,
    чтобы adminui и mediaworker делили сессию. Если запрос пришёл с другого
    домена (например, отдельного ``CLIENT_DOMAIN`` через reverse proxy),
    возвращается ``None`` (host-only cookie), иначе браузер отвергнет cookie.
    """
    domain = cfg.cookie_domain
    if not domain or request is None:
        return domain
    raw_host = request.headers.get("host") or ""
    if cfg.trusted_proxies_list:
        raw_host = request.headers.get("x-forwarded-host") or raw_host
    host = raw_host.split(",", 1)[0].split(":", 1)[0].strip().lower()
    if not host:
        return domain
    if host == domain or host.endswith(f".{domain}"):
        return domain
    return None


def set_auth_cookies(
    response: Response,
    cfg: AppConfig,
    *,
    access_token: str,
    refresh_token: str,
    request: Request | None = None,
) -> None:
    """Выставить обе auth-cookie на ответ (login/register/refresh)."""
    domain = _resolve_cookie_domain(cfg, request)
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=cfg.ACCESS_TOKEN_TTL,
        httponly=True,
        secure=not cfg.DEBUG,
        samesite="strict",
        domain=domain,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=cfg.REFRESH_TOKEN_TTL,
        httponly=True,
        secure=not cfg.DEBUG,
        samesite="strict",
        domain=domain,
        # Refresh-токен нужен только для /auth/refresh и /auth/logout —
        # уже суженный path не даёт ему уходить с каждым обычным запросом.
        path="/api/v1/auth",
    )


def clear_auth_cookies(
    response: Response, cfg: AppConfig, *, request: Request | None = None
) -> None:
    """Снять обе auth-cookie (logout)."""
    domain = _resolve_cookie_domain(cfg, request)
    response.delete_cookie(
        ACCESS_COOKIE, domain=domain, path="/", samesite="strict"
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        domain=domain,
        path="/api/v1/auth",
        samesite="strict",
    )


__all__ = ["ACCESS_COOKIE", "REFRESH_COOKIE", "set_auth_cookies", "clear_auth_cookies"]
