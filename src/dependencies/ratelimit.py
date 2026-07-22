"""FastAPI-зависимость ограничения частоты запросов (rate limiting)."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Callable

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import AppConfig
from dependencies.settings import get_settings_mngr
from models.system_settings import SystemSettingsMngr
from security.ratelimit import LimitRule, RateLimiter

log = logging.getLogger("saviorbill.ratelimit")

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


# Переопределения правил лимитов хранятся в таблице `settings` (не в чистом
# Valkey — см. IMPLEMENTATION_PLAN.md §0.4), значение — JSON {"max_hits", "window"}.
# `SystemSettingsMngr` сам кэширует прочитанные значения в Valkey, поэтому
# отдельного ручного кэша override'ов здесь не требуется.
def _kind_setting_key(kind: LimitKind) -> str:
    return f"ratelimit.kind.{kind.value}"


def _scope_setting_key(scope: str) -> str:
    return f"ratelimit.scope.{scope}"


async def _load_override(settings: SystemSettingsMngr, key: str) -> LimitRule | None:
    """Прочитать override правила по ключу настройки (или ``None``, если не задан
    / повреждён — повреждённое значение не должно валить запрос, только лог)."""
    raw = await settings.get(key)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return LimitRule(int(data["max_hits"]), int(data["window"]))
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("invalid rate limit override at %s: %s", key, exc)
        return None


async def _resolve_rule(
    settings: SystemSettingsMngr, cfg: AppConfig, scope: str, kind: LimitKind
) -> LimitRule:
    """Определить действующее правило: scope-override > kind-override > ENV-дефолт.

    :arg settings: менеджер настроек (БД + кэш Valkey внутри).
    :arg cfg: конфигурация приложения (ENV-дефолт).
    :arg scope: имя точки (для персонального переопределения).
    :arg kind: категория лимита.
    :return: действующее правило лимита.
    """
    rule = await _load_override(settings, _scope_setting_key(scope))
    if rule is not None:
        return rule
    rule = await _load_override(settings, _kind_setting_key(kind))
    if rule is not None:
        return rule
    return _rule_for(cfg, kind)


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
        settings: SystemSettingsMngr = Depends(get_settings_mngr),
    ) -> None:
        cfg: AppConfig = request.app.state.settings
        if not cfg.RATE_LIMIT_ENABLED:
            return
        rule = await _resolve_rule(settings, cfg, scope, kind)
        limiter = RateLimiter(request.app.state.valkey)
        res = await limiter.hit(scope, _client_ident(request, cred), rule)
        if not res.allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many requests, try again later",
                headers={"Retry-After": str(res.retry_after)},
            )
        response.headers["X-RateLimit-Remaining"] = str(res.remaining)

    # Метки для авто-документации ограничений в OpenAPI (см. utils/openapi.py).
    _dep._rate_limit_scope = scope
    _dep._rate_limit_kind = kind
    return _dep


__all__ = ["LimitKind", "rate_limit"]
