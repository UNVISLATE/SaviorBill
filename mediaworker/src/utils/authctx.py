"""Единые auth-хелперы для роутов mediaworker.

Раньше ``_client_ip``/``_bearer``/``_authenticate``/``_authorize`` были
продублированы буквально (copy-paste) в ``upload.py`` и ``serve.py``, а
``kinds.py`` держал свою урезанную копию (``_soft_authenticate``) — при
любом изменении логики (например, добавлении нового поля в проверку бана)
нужно было помнить о всех копиях. Вынесено сюда одним модулем;
``add_preview``/``replace_thumb``-специфичная проверка владения медиа
(``_authorize_media_owner`` в ``serve.py``) осталась на месте, т.к. она
не переиспользуется больше нигде и завязана на ``db.media_owner``.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from utils import security
from utils.config import Config


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
    """Достать сырой Bearer-токен из заголовка Authorization; 401 если его нет."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    return auth.split(" ", 1)[1].strip()


async def authenticate(request: Request) -> int:
    """Проверить access-JWT и вернуть id аккаунта; 401 при невалидном токене."""
    cfg: Config = request.app.state.cfg
    token = bearer(request)
    try:
        return security.account_id(
            token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss
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
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        return security.account_id(
            token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken:
        return None


__all__ = [
    "client_ip",
    "bearer",
    "authenticate",
    "authorize",
    "soft_authenticate",
]
