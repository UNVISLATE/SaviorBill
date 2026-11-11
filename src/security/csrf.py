"""Лёгкая CSRF-защита для cookie-based авторизации.

Auth-cookie (``sb_access``/``sb_refresh``, см. ``security/sec/cookies.py``)
ставится с ``SameSite=Strict`` — это уже блокирует отправку cookie в
запросах, инициированных с чужого сайта (классический CSRF), в любом
современном браузере. Эта миддлварь — defense-in-depth поверх SameSite (на
случай нестандартного клиента/старого браузера, который её не соблюдает):
для небезопасных методов, аутентифицированных именно cookie (не
``Authorization``-заголовком, который CSRF не умеет подделать), сверяет
``Origin`` с разрешённым списком (``CORS_ORIGINS``).

Эндпоинты аутентификации (логин, регистрация, refresh, сброс пароля) и
внешние webhook'и (платежи/OAuth-callback) освобождены от проверки: они не
используют ``sb_access`` для авторизации действий текущей сессии и не
должны отклоняться при наличии остаточных cookie в клиенте.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.config import AppConfig
from security.sec.cookies import ACCESS_COOKIE

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Эндпоинты, не авторизующие действия через sb_access
_CSRF_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/password/reset/request",
        "/api/v1/auth/password/reset/confirm",
    }
)

_CSRF_EXEMPT_PREFIXES = (
    "/api/v1/callback/",
)


def _is_exempt(path: str) -> bool:
    if path in _CSRF_EXEMPT_PATHS:
        return True
    return path.startswith(_CSRF_EXEMPT_PREFIXES)


def _origin_of(url: str) -> str:
    """``scheme://host[:port]`` из Origin (уже таков) или Referer (с путём)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme else url


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def _host_of(url_or_host: str) -> str:
    val = url_or_host.strip().lower()
    if "://" in val:
        return (urlsplit(val).hostname or "").lower()
    if val.startswith("["):
        end = val.find("]")
        return val[1:end] if end != -1 else val
    return val.split(":", 1)[0]


def _is_loopback(url_or_host: str | None) -> bool:
    if not url_or_host:
        return False
    return _host_of(url_or_host) in _LOOPBACK_HOSTS


def _origin_allowed(origin: str, allowed: list[str]) -> bool:
    norm = _origin_of(origin).rstrip("/").lower()
    return norm in {_origin_of(o).rstrip("/").lower() for o in allowed if o}


def _fallback_origins(request: Request, cfg: object) -> list[str]:
    origins: list[str] = []
    host = request.headers.get("host")
    if host:
        origins.append(f"{request.url.scheme or 'http'}://{host}")
    for attr in ("PUBLIC_URL", "MEDIA_PUBLIC_URL"):
        val = getattr(cfg, attr, None)
        if isinstance(val, str) and val.strip():
            origins.append(val.strip())
    for attr in ("DOMAIN", "MEDIA_DOMAIN"):
        val = getattr(cfg, attr, None)
        if isinstance(val, str) and val.strip():
            dom = val.strip().rstrip("/")
            if "://" in dom:
                origins.append(dom)
            else:
                origins.extend([f"https://{dom}", f"http://{dom}"])
    return origins


def _request_origin_allowed(request: Request, cfg: object, origin: str) -> bool:
    allowed = [
        *cfg.cors_origins_list,
        *_fallback_origins(request, cfg),
    ]
    if allowed and _origin_allowed(origin, allowed):
        return True
    # Локальный dev через Vite/webpack proxy (localhost:5173/5174 -> 127.0.0.1:8000):
    # changeOrigin меняет Host-порт на бэкендный, но оба хоста остаются loopback.
    if _is_loopback(origin) and (
        _is_loopback(request.headers.get("host")) or bool(getattr(cfg, "DEBUG", False))
    ):
        return True
    return False


class CookieCSRFMiddleware(BaseHTTPMiddleware):
    """Отклонить небезопасный запрос с чужим ``Origin``, если auth — по cookie."""

    def __init__(self, app, cfg: AppConfig) -> None:
        super().__init__(app)
        self._cfg = cfg

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if (
            request.method not in _SAFE_METHODS
            and not _is_exempt(request.url.path)
            and not request.headers.get("authorization")
            and request.cookies.get(ACCESS_COOKIE)
        ):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if not origin or not _request_origin_allowed(request, self._cfg, origin):
                return JSONResponse(
                    {"detail": "cross-origin request rejected"}, status_code=403
                )
        return await call_next(request)


__all__ = ["CookieCSRFMiddleware", "_is_exempt"]
