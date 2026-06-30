"""FastAPI-зависимость ограничения частоты запросов (rate limiting)."""

from __future__ import annotations

from enum import Enum
from typing import Callable

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.config import AppConfig
from utils.ratelimit import LimitRule, RateLimiter

_bearer = HTTPBearer(auto_error=False)


class LimitKind(str, Enum):
    """Именованные категории лимитов (правило берётся из конфигурации)."""

    DEFAULT = "default"
    AUTH = "auth"
    MAIL = "mail"
    SENSITIVE = "sensitive"


def _rule_for(cfg: AppConfig, kind: LimitKind) -> LimitRule:
    """Достать правило лимита из конфигурации по категории."""
    if kind is LimitKind.AUTH:
        return LimitRule(cfg.RATE_LIMIT_AUTH_MAX, cfg.RATE_LIMIT_AUTH_WINDOW)
    if kind is LimitKind.MAIL:
        return LimitRule(cfg.RATE_LIMIT_MAIL_MAX, cfg.RATE_LIMIT_MAIL_WINDOW)
    if kind is LimitKind.SENSITIVE:
        return LimitRule(cfg.RATE_LIMIT_SENSITIVE_MAX, cfg.RATE_LIMIT_SENSITIVE_WINDOW)
    return LimitRule(cfg.RATE_LIMIT_DEFAULT_MAX, cfg.RATE_LIMIT_DEFAULT_WINDOW)


def _client_ident(request: Request, cred: HTTPAuthorizationCredentials | None) -> str:
    """Идентификатор клиента: токен (если передан) либо IP."""
    if cred is not None and cred.credentials:
        # Не валидируем токен здесь — для лимита достаточно его как метки клиента.
        return "tok:" + cred.credentials[-32:]
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def rate_limit(scope: str, kind: LimitKind = LimitKind.DEFAULT) -> Callable:
    """Сконструировать зависимость лимита для роута.

    :arg scope: уникальное имя точки (для разделения счётчиков).
    :arg kind:  категория лимита (правило из конфигурации).
    """

    async def _dep(
        request: Request,
        response: Response,
        cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> None:
        cfg: AppConfig = request.app.state.settings
        if not cfg.RATE_LIMIT_ENABLED:
            return
        rule = _rule_for(cfg, kind)
        limiter = RateLimiter(request.app.state.valkey)
        res = await limiter.hit(scope, _client_ident(request, cred), rule)
        if not res.allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="слишком много запросов, попробуйте позже",
                headers={"Retry-After": str(res.retry_after)},
            )
        response.headers["X-RateLimit-Remaining"] = str(res.remaining)

    # Метки для авто-документации ограничений в OpenAPI (см. utils/openapi.py).
    _dep._rate_limit_scope = scope
    _dep._rate_limit_kind = kind
    return _dep


__all__ = ["LimitKind", "rate_limit"]
