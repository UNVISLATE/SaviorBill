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
from services.security_monitor import check_and_apply_autoban, log_security_event
from utils.degrade import VALKEY_ERRORS, note_degraded

log = logging.getLogger("saviorbill.ratelimit")


class LimitKind(str, Enum):
    """Именованные категории лимитов (правило берётся из конфигурации)."""

    DEFAULT = "default"
    AUTH = "auth"
    MAIL = "mail"
    SENSITIVE = "sensitive"
    CRITICAL = "critical"


BURST_DEFAULTS: dict[LimitKind, tuple[int, int]] = {
    LimitKind.DEFAULT: (15, 1),
    LimitKind.AUTH: (3, 1),
    LimitKind.MAIL: (1, 5),
    LimitKind.SENSITIVE: (5, 1),
    LimitKind.CRITICAL: (5, 1),
}


def _rule_for(cfg: AppConfig, kind: LimitKind) -> LimitRule:
    """Достать правило лимита из конфигурации по категории (ENV-дефолт)."""
    if kind is LimitKind.AUTH:
        return LimitRule(cfg.RATE_LIMIT_AUTH_MAX, cfg.RATE_LIMIT_AUTH_WINDOW)
    if kind is LimitKind.MAIL:
        return LimitRule(cfg.RATE_LIMIT_MAIL_MAX, cfg.RATE_LIMIT_MAIL_WINDOW)
    if kind in (LimitKind.SENSITIVE, LimitKind.CRITICAL):
        return LimitRule(cfg.RATE_LIMIT_SENSITIVE_MAX, cfg.RATE_LIMIT_SENSITIVE_WINDOW)
    return LimitRule(cfg.RATE_LIMIT_DEFAULT_MAX, cfg.RATE_LIMIT_DEFAULT_WINDOW)


def _burst_rule_for(kind: LimitKind) -> LimitRule:
    """Дефолтное правило всплеска (burst) для категории."""
    hits, win = BURST_DEFAULTS.get(kind, (15, 1))
    return LimitRule(hits, win)


def _kind_setting_key(kind: LimitKind) -> str:
    return f"ratelimit.kind.{kind.value}"


def _scope_setting_key(scope: str) -> str:
    return f"ratelimit.scope.{scope}"


async def _load_override(
    settings: SystemSettingsMngr, key: str
) -> tuple[LimitRule | None, LimitRule | None]:
    """Прочитать override правил (основное + burst) по ключу настройки."""
    raw = await settings.get(key)
    if raw is None:
        return None, None
    try:
        data = json.loads(raw)
        main_rule = LimitRule(int(data["max_hits"]), int(data["window"]))
        burst_rule = None
        if "burst_hits" in data and data["burst_hits"] is not None:
            burst_rule = LimitRule(
                int(data["burst_hits"]), int(data.get("burst_window", 1))
            )
        return main_rule, burst_rule
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("invalid rate limit override at %s: %s", key, exc)
        return None, None


async def _resolve_rules(
    settings: SystemSettingsMngr, cfg: AppConfig, scope: str, kind: LimitKind
) -> tuple[LimitRule, LimitRule]:
    """Определить действующие правила (основное и burst): scope-override > kind-override > ENV-дефолт."""
    s_main, s_burst = await _load_override(settings, _scope_setting_key(scope))
    k_main, k_burst = await _load_override(settings, _kind_setting_key(kind))

    main_rule = s_main or k_main or _rule_for(cfg, kind)
    burst_rule = s_burst or k_burst or _burst_rule_for(kind)
    return main_rule, burst_rule


async def _resolve_rule(
    settings: SystemSettingsMngr, cfg: AppConfig, scope: str, kind: LimitKind
) -> LimitRule:
    main_rule, _ = await _resolve_rules(settings, cfg, scope, kind)
    return main_rule


def _client_ip(request: Request) -> str:
    """IP клиента как ключ лимитера для публичных (неаутентифицированных) роутов."""
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def _authenticated_ident(acc: UserModel) -> str:
    """Ключ лимитера по уже провалидированному аккаунту (приватные роуты)."""
    return "user:" + str(acc.id)


def rate_limit(
    scope: str, kind: LimitKind = LimitKind.DEFAULT, require_auth: bool = False
) -> Callable:
    """Сконструировать зависимость лимита для роута."""

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
        await _enforce_ip_guard(
            request, response, settings, _client_ip(request), scope, kind
        )

    _dep = _dep_authenticated if require_auth else _dep_public
    _dep._rate_limit_scope = scope
    _dep._rate_limit_kind = kind
    return _dep


async def _enforce_ip_guard(
    request: Request,
    response: Response,
    settings: SystemSettingsMngr,
    ident: str,
    scope: str,
    kind: LimitKind,
) -> None:
    app_state = getattr(getattr(request, "app", None), "state", None)
    cfg: AppConfig = getattr(app_state, "settings", None) if app_state else None
    if not cfg or not cfg.RATE_LIMIT_ENABLED:
        return
    try:
        base_rule = await _resolve_rule(settings, cfg, scope, kind)
        ip_rule = LimitRule(base_rule.max_hits * 5, base_rule.window)
        limiter = RateLimiter(app_state.valkey)
        res = await limiter.hit(f"{scope}:ip_guard", ident, ip_rule)
    except VALKEY_ERRORS as exc:
        note_degraded("ratelimit", exc)
        return
    if not res.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests from your IP, try again later",
            headers={"Retry-After": str(res.retry_after)},
        )


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

    try:
        rule, burst_rule = await _resolve_rules(settings, cfg, scope, kind)
        limiter = RateLimiter(request.app.state.valkey)

        # 1. Burst Rate Limit (1-секундный всплеск)
        if burst_rule is not None:
            burst_res = await limiter.hit(f"{scope}:burst", ident, burst_rule)
            if not burst_res.allowed:
                client_ip = request.client.host if request.client else "unknown"
                vk = request.app.state.valkey
                trace_id = getattr(getattr(request, "state", None), "trace_id", None)
                await log_security_event(
                    vk,
                    ip=client_ip,
                    action="burst_rate_limited",
                    reason=f"Превышен всплеск (burst): {burst_rule.max_hits} за {burst_rule.window}с ({scope})",
                    scope=scope,
                    kind=kind.value,
                    details=f"Retry-After: {burst_res.retry_after}s",
                    trace_id=trace_id,
                )
                was_banned = await check_and_apply_autoban(
                    vk, client_ip, settings, trace_id=trace_id
                )
                if was_banned:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        detail="too many rate limit violations: your IP has been temporarily blocked",
                        headers={"Retry-After": str(burst_res.retry_after)},
                    )
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="burst rate limit exceeded, please slow down",
                    headers={"Retry-After": str(burst_res.retry_after)},
                )

        # 2. Основное скользящее окно
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
        client_ip = request.client.host if request.client else "unknown"
        vk = request.app.state.valkey
        trace_id = getattr(getattr(request, "state", None), "trace_id", None)
        await log_security_event(
            vk,
            ip=client_ip,
            action="rate_limited",
            reason=f"Превышен лимит {rule.max_hits} за {rule.window}с ({scope})",
            scope=scope,
            kind=kind.value,
            details=f"Retry-After: {res.retry_after}s",
            trace_id=trace_id,
        )
        was_banned = await check_and_apply_autoban(
            vk, client_ip, settings, trace_id=trace_id
        )
        if was_banned:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="too many rate limit violations: your IP has been temporarily blocked",
                headers={"Retry-After": str(res.retry_after)},
            )
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
    """Публичная обёртка над ``_enforce`` для условного лимитирования."""
    await _enforce(request, response, settings, ident, scope, kind)


def authenticated_ident(acc: UserModel) -> str:
    """Публичный алиас :func:`_authenticated_ident` для использования вне модуля."""
    return _authenticated_ident(acc)


__all__ = [
    "LimitKind",
    "BURST_DEFAULTS",
    "_burst_rule_for",
    "_rule_for",
    "_kind_setting_key",
    "rate_limit",
    "enforce_rate_limit",
    "authenticated_ident",
]
