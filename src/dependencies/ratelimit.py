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
    """Достать правило лимита из конфигурации по категории (ENV-дефолт)."""
    if kind is LimitKind.AUTH:
        return LimitRule(cfg.RATE_LIMIT_AUTH_MAX, cfg.RATE_LIMIT_AUTH_WINDOW)
    if kind is LimitKind.MAIL:
        return LimitRule(cfg.RATE_LIMIT_MAIL_MAX, cfg.RATE_LIMIT_MAIL_WINDOW)
    if kind is LimitKind.SENSITIVE:
        return LimitRule(cfg.RATE_LIMIT_SENSITIVE_MAX, cfg.RATE_LIMIT_SENSITIVE_WINDOW)
    return LimitRule(cfg.RATE_LIMIT_DEFAULT_MAX, cfg.RATE_LIMIT_DEFAULT_WINDOW)


# Префикс персистентных ключей настроек лимитов в Valkey. Значения переопределяются
# админом в рантайме без рестарта; ENV-дефолты сидятся при старте через SETNX.
_RLCFG = "rlcfg:"


def _kind_keys(kind: LimitKind) -> tuple[str, str]:
    return f"{_RLCFG}kind:{kind.value}:max", f"{_RLCFG}kind:{kind.value}:window"


def _scope_keys(scope: str) -> tuple[str, str]:
    return f"{_RLCFG}scope:{scope}:max", f"{_RLCFG}scope:{scope}:window"


async def seed_rate_limits(vk, cfg: AppConfig) -> None:
    """Записать ENV-дефолты лимитов в Valkey (не перетирая ручные правки).

    Вызывается на каждом старте. Использует SETNX, поэтому админ-переопределения
    переживают рестарт, а ENV задаёт лишь первоначальные значения.

    :arg vk: клиент Valkey.
    :arg cfg: конфигурация приложения (источник ENV-дефолтов).
    """
    for kind in LimitKind:
        rule = _rule_for(cfg, kind)
        kmax, kwin = _kind_keys(kind)
        await vk.set(kmax, rule.max_hits, nx=True)
        await vk.set(kwin, rule.window, nx=True)


async def _resolve_rule(vk, cfg: AppConfig, scope: str, kind: LimitKind) -> LimitRule:
    """Определить действующее правило: scope-override > kind > ENV-дефолт.

    Читает переопределения из Valkey (одним MGET). Отсутствие ключей — падение на
    ENV-дефолт, чтобы лимиты работали и без сидинга.

    :arg vk: клиент Valkey.
    :arg cfg: конфигурация приложения (ENV-дефолт).
    :arg scope: имя точки (для персонального переопределения).
    :arg kind: категория лимита.
    :return: действующее правило лимита.
    """
    smax, swin = _scope_keys(scope)
    kmax, kwin = _kind_keys(kind)
    vals = await vk.mget([smax, swin, kmax, kwin])
    base = _rule_for(cfg, kind)
    max_hits = int(vals[0] or vals[2] or base.max_hits)
    window = int(vals[1] or vals[3] or base.window)
    return LimitRule(max_hits, window)


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
        rule = await _resolve_rule(request.app.state.valkey, cfg, scope, kind)
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


__all__ = ["LimitKind", "rate_limit", "seed_rate_limits"]
