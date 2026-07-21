"""Авторизация WS-хендшейка для собственных realtime-роутов mediaworker
(``/api/media/logs/...``).

Копия схемы billing (``apiws/authctx.py::authorize_ws``): без токена в URL
(история браузера/логи прокси) — клиент шлёт первым текстовым сообщением
``{"token": "<access-JWT>"}`` сразу после установления соединения. Здесь —
не переиспользование кода billing (отдельный деплоймент), а тот же паттерн
поверх уже имеющихся в mediaworker примитивов (``utils/security.py`` —
проверка JWT, ``utils/db.py`` — права роли из общей Postgres).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from utils import security
from utils.config import Config
from utils.rbac import has_perm

HANDSHAKE_TIMEOUT = 30


async def authenticate_ws_payload(ws: WebSocket) -> tuple[int, dict] | None:
    """Дождаться первого фрейма ``{"token": "<access-JWT>", ...}``, проверить
    токен и вернуть ``(acc_id, payload)`` — ``payload`` целиком, чтобы роуты
    с доп. полями в хендшейке (например ``watch: [...]`` в ``media/mine``) не
    читали сырой фрейм второй раз. При любой неудаче сам закрывает соединение
    кодом ``4401`` и возвращает ``None``.
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=HANDSHAKE_TIMEOUT)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=4401)
        return None

    try:
        payload = json.loads(raw)
        token = payload["token"]
    except (json.JSONDecodeError, KeyError, TypeError):
        await ws.close(code=4401)
        return None

    cfg: Config = ws.app.state.cfg
    try:
        acc_id = security.account_id(token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss)
    except security.InvalidToken:
        await ws.close(code=4401)
        return None
    return acc_id, payload


async def authenticate_ws(ws: WebSocket) -> int | None:
    """Как ``authenticate_ws_payload``, но без доп. полей хендшейка — вернуть
    только id аккаунта (без проверки прав роли, см. ``authorize_ws`` для
    варианта с RBAC)."""
    result = await authenticate_ws_payload(ws)
    return result[0] if result is not None else None


async def authorize_ws(ws: WebSocket, required_perm: str) -> int | None:
    """Дождаться токена и проверить право ``required_perm``.

    При любой неудаче сам закрывает соединение кодом ``4401`` и возвращает
    ``None`` — вызывающая сторона просто прекращает обработку. При успехе —
    id аккаунта (на случай, если понадобится в будущем, например для аудита).
    """
    acc_id = await authenticate_ws(ws)
    if acc_id is None:
        return None

    db = ws.app.state.db
    acc = await db.account(acc_id)
    if acc is None:
        await ws.close(code=4401)
        return None
    if not has_perm(acc.perms, required_perm):
        await ws.close(code=4401)
        return None
    return acc_id


__all__ = ["authenticate_ws_payload", "authenticate_ws", "authorize_ws", "HANDSHAKE_TIMEOUT"]
