"""FastAPI-зависимость ограничения частоты запросов (rate limiting)."""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Callable

from fastapi import Depends, HTTPException, Request, Response, status

from core.config import AppConfig
from dependencies.auth import get_current_acc
from dependencies.settings import get_settings_mngr
from models.system_settings import SystemSettingsMngr
from models.user import UserModel
from security.ratelimit import LimitRule, RateLimiter
from utils.degrade import VALKEY_ERRORS, note_degraded

log = logging.getLogger("saviorbill.ratelimit")


class LimitKind(str, Enum):
    """Именованные категории лимитов (правило берётся из конфигурации)."""

    DEFAULT = "default"
    AUTH = "auth"
    MAIL = "mail"
    SENSITIVE = "sensitive"
    CRITICAL = "critical"


def _rule_for(cfg: AppConfig, kind: LimitKind) -> LimitRule:
    """Достать правило лимита из конфигурации по категории (ENV-дефолт)."""
    if kind is LimitKind.AUTH:
        return LimitRule(cfg.RATE_LIMIT_AUTH_MAX, cfg.RATE_LIMIT_AUTH_WINDOW)
    if kind is LimitKind.MAIL:
        return LimitRule(cfg.RATE_LIMIT_MAIL_MAX, cfg.RATE_LIMIT_MAIL_WINDOW)
    if kind in (LimitKind.SENSITIVE, LimitKind.CRITICAL):
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


def _client_ip(request: Request) -> str:
    """IP клиента как ключ лимитера для публичных (неаутентифицированных) роутов.

    Не используем сырой заголовок ``Authorization`` как альтернативу — он не
    валидируется здесь, и атакующий, подставляя новый случайный Bearer на
    каждый запрос, получал бы новый бакет лимитера и обходил ограничение
    (см. AUDIT.md §2.1). Для приватных роутов используется
    ``_authenticated_ident`` — ключ по уже провалидированному ``user_id``.
    """
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def _authenticated_ident(acc: UserModel) -> str:
    """Ключ лимитера по уже провалидированному аккаунту (приватные роуты)."""
    return "user:" + str(acc.id)


def rate_limit(
    scope: str, kind: LimitKind = LimitKind.DEFAULT, require_auth: bool = False
) -> Callable:
    """Сконструировать зависимость лимита для роута.

    :arg scope: уникальное имя точки (для разделения счётчиков).
    :arg kind:  категория лимита (правило из конфигурации).
    :arg require_auth: ``True`` для приватных роутов — ключ лимитера строится
        по ``user_id`` из провалидированного здесь же access-токена (форсирует
        аутентификацию раньше самого лимитера, а не полагается на порядок
        выполнения соседних FastAPI-зависимостей). ``False`` (по умолчанию) —
        публичный роут, ключ всегда IP, сырой ``Authorization`` не учитывается.
    """

    async def _dep_public(
        request: Request,
        response: Response,
        settings: SystemSettingsMngr = Depends(get_settings_mngr),
    ) -> None:
        await _enforce(request, response, settings, _client_ip(request), scope, kind)

    async def _dep_authenticated(
        request: Request,
        response: Response,
        acc: UserModel = Depends(get_current_acc),
        settings: SystemSettingsMngr = Depends(get_settings_mngr),
    ) -> None:
        await _enforce(
            request, response, settings, _authenticated_ident(acc), scope, kind
        )

    _dep = _dep_authenticated if require_auth else _dep_public

    # Метки для авто-документации ограничений в OpenAPI (см. utils/openapi.py).
    _dep._rate_limit_scope = scope
    _dep._rate_limit_kind = kind
    return _dep


async def _enforce(
    request: Request,
    response: Response,
    settings: SystemSettingsMngr,
    ident: str,
    scope: str,
    kind: LimitKind,
) -> None:
    cfg: AppConfig = request.app.state.settings
    if not cfg.RATE_LIMIT_ENABLED:
        return
    # Valkey недоступен — пропускаем запрос, а не роняем весь роут:
    # лимитер вспомогательный, отказ в обслуживании хуже отсутствия лимита.
    try:
        rule = await _resolve_rule(settings, cfg, scope, kind)
        limiter = RateLimiter(request.app.state.valkey)
        res = await limiter.hit(scope, ident, rule)
    except VALKEY_ERRORS as exc:
        note_degraded("ratelimit", exc)
        if kind in (LimitKind.AUTH, LimitKind.SENSITIVE, LimitKind.CRITICAL):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="protection service temporarily unavailable",
                headers={"Retry-After": "5"},
            ) from None
        return
    if not res.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests, try again later",
            headers={"Retry-After": str(res.retry_after)},
        )
    response.headers["X-RateLimit-Remaining"] = str(res.remaining)


async def enforce_rate_limit(
    request: Request,
    response: Response,
    settings: SystemSettingsMngr,
    ident: str,
    scope: str,
    kind: LimitKind = LimitKind.DEFAULT,
) -> None:
    """Публичная обёртка над ``_enforce`` для условного лимитирования вне
    ``rate_limit()`` — когда лимит нужен только при определённом значении
    query-параметра (см. ``catalog.py::get_service`` промо-превью)."""
    await _enforce(request, response, settings, ident, scope, kind)


def authenticated_ident(acc: UserModel) -> str:
    """Публичный алиас :func:`_authenticated_ident` для использования вне модуля."""
    return _authenticated_ident(acc)


__all__ = ["LimitKind", "rate_limit", "enforce_rate_limit", "authenticated_ident"]
