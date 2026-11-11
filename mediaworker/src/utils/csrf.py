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
    if _is_loopback(origin) and (
        _is_loopback(request.headers.get("host")) or bool(getattr(cfg, "DEBUG", False))
    ):
        return True
    return False


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
            if not origin or not _request_origin_allowed(request, self._cfg, origin):
                return JSONResponse(
                    {"detail": "cross-origin request rejected"}, status_code=403
                )
        return await call_next(request)


__all__ = ["CookieCSRFMiddleware"]
