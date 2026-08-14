"""Лёгкая CSRF-защита для cookie-based авторизации.

Auth-cookie (``sb_access``/``sb_refresh``, см. ``security/sec/cookies.py``)
ставится с ``SameSite=Strict`` — это уже блокирует отправку cookie в
запросах, инициированных с чужого сайта (классический CSRF), в любом
современном браузере. Эта миддлварь — defense-in-depth поверх SameSite (на
случай нестандартного клиента/старого браузера, который её не соблюдает):
для небезопасных методов, аутентифицированных именно cookie (не
``Authorization``-заголовком, который CSRF не умеет подделать), сверяет
``Origin`` с разрешённым списком (``CORS_ORIGINS``).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.config import AppConfig
from security.sec.cookies import ACCESS_COOKIE

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _origin_of(url: str) -> str:
    """``scheme://host[:port]`` из Origin (уже таков) или Referer (с путём)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme else url


def _origin_allowed(origin: str, allowed: list[str]) -> bool:
    origin = _origin_of(origin).rstrip("/")
    return origin in {o.rstrip("/") for o in allowed}


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
            and not request.headers.get("authorization")
            and request.cookies.get(ACCESS_COOKIE)
        ):
            origin = request.headers.get("origin") or request.headers.get("referer")
            allowed = self._cfg.cors_origins_list
            if not origin or (allowed and not _origin_allowed(origin, allowed)):
                return JSONResponse(
                    {"detail": "cross-origin request rejected"}, status_code=403
                )
        return await call_next(request)


__all__ = ["CookieCSRFMiddleware"]
