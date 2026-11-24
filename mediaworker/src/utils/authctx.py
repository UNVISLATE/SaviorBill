"""Единые auth-хелперы для роутов mediaworker."""

from __future__ import annotations

import json
import time

from fastapi import HTTPException, Request, status

from utils import security
from utils.config import Config

_JWKS_CACHE_TTL_SEC = 60.0


async def _resolve_jwt_keys(request: Request) -> dict[str, str]:
    """Получить публичный key-ring JWT: из Valkey ``auth:jwks`` (с кэшем 60с) + fallback на файлы/ENV."""
    cfg: Config = request.app.state.cfg
    keys = cfg.jwt_public_keys()

    vk = getattr(request.app.state, "vk", None)
    if vk is None:
        return keys

    now = time.monotonic()
    cached = getattr(request.app.state, "_jwks_cache", None)
    cached_at = getattr(request.app.state, "_jwks_cached_at", 0.0)
    if isinstance(cached, dict) and (now - cached_at) < _JWKS_CACHE_TTL_SEC:
        return {**cached, **keys}

    try:
        raw = await vk.get("auth:jwks")
        if raw:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            parsed = json.loads(text)
            vk_keys = parsed.get("keys") if isinstance(parsed, dict) else None
            if isinstance(vk_keys, dict):
                clean = {str(k): str(v) for k, v in vk_keys.items() if k and v}
                request.app.state._jwks_cache = clean
                request.app.state._jwks_cached_at = now
                return {**clean, **keys}
    except Exception:  # noqa: BLE001 — fallback на локальные ключи
        pass
    return keys

# Должно совпадать с billing (см. ``src/security/sec/cookies.py``) — общий
# корневой домен (``AppConfig.cookie_domain``) делает эту cookie видимой и
# billing, и mediaworker.
ACCESS_COOKIE = "sb_access"


def client_ip(request: Request) -> str:
    """IP клиента.

    Реальный источник — TCP-peer (``request.client.host``). Значение из
    ``X-Forwarded-For`` подставляется сюда автоматически uvicorn'овским
    ``ProxyHeadersMiddleware``, но только если пир — доверенный реверс-прокси
    из ``TRUSTED_PROXIES`` (см. ``app.py``); без доверенного прокси в списке
    заголовок полностью игнорируется — раньше он читался напрямую и без
    проверки, что позволяло клиенту подделать свой IP произвольным
    заголовком.
    """
    return request.client.host if request.client else "0.0.0.0"


def bearer(request: Request) -> str:
    """Достать access-токен: заголовок Authorization в приоритете, иначе cookie.

    Заголовок — для не-браузерных клиентов (скрипты, billing-to-mediaworker и
    т.п.); cookie ``sb_access`` (httpOnly) — для adminui, см.
    ``src/security/sec/cookies.py``. 401, если нет ни того, ни другого.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    return token


async def authenticate(request: Request) -> int:
    """Проверить access-JWT и вернуть id аккаунта; 401 при невалидном токене."""
    cfg: Config = request.app.state.cfg
    token = bearer(request)
    keys = await _resolve_jwt_keys(request)
    try:
        return security.account_id(
            token, keys, cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


async def authorize(request: Request, acc_id: int) -> tuple[dict | None, str | None]:
    """Прочитать права аккаунта; вернуть ``(perms, role_key)``. 401 если аккаунта нет.

    ``banned`` — не хардкодится отдельно: это просто роль, которую назначают
    при бане, без прав по умолчанию. Доступ к конкретным действиям решает
    исключительно ``has_perm`` на правах роли — если явно выдать роли
    ``banned`` конкретное право, оно будет работать.
    """
    db = request.app.state.db
    acc = await db.account(acc_id)
    if acc is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")
    return acc.perms, acc.role_key


async def soft_authenticate(request: Request) -> int | None:
    """Как ``authenticate()``, но без исключений — ``None`` при отсутствии/невалидности токена.

    Используется там, где авторизация опциональна (``kinds.py`` — лимиты
    показываются только если токен есть и валиден, но сам список форматов
    доступен анонимно).
    """
    cfg: Config = request.app.state.cfg
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    else:
        token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    keys = await _resolve_jwt_keys(request)
    try:
        return security.account_id(
            token, keys, cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken:
        return None


__all__ = [
    "ACCESS_COOKIE",
    "client_ip",
    "bearer",
    "authenticate",
    "authorize",
    "soft_authenticate",
]
