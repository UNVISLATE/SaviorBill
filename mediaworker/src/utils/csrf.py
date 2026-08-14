"""Лёгкая CSRF-защита для cookie-based авторизации (см. billing/src/security/csrf.py).

Тот же принцип: ``SameSite=Strict`` на auth-cookie уже блокирует классический
CSRF в современных браузерах; эта миддлварь — defense-in-depth поверх него
для небезопасных методов, аутентифицированных именно cookie (не
``Authorization``-заголовком).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from utils.authctx import ACCESS_COOKIE
from utils.config import Config

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme else url


def _origin_allowed(origin: str, allowed: list[str]) -> bool:
    origin = _origin_of(origin).rstrip("/")
    return origin in {o.rstrip("/") for o in allowed}


class CookieCSRFMiddleware(BaseHTTPMiddleware):
    """Отклонить небезопасный запрос с чужим ``Origin``, если auth — по cookie."""

    def __init__(self, app, cfg: Config) -> None:
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
