"""Общая логика авторизации WS-хендшейка для ``/apiws/*`` (без токена в URL)"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from models.user import UserMngr, UserModel
from security.rbac import has_perm
from security.sec import jwt as jwtu

HANDSHAKE_TIMEOUT = 30


async def authenticate_ws(ws: WebSocket) -> UserModel | None:
    """Дождаться первого фрейма с токеном и вернуть аккаунт.

    При любой неудаче сам закрывает соединение кодом ``4401`` и возвращает
    ``None`` — вызывающая сторона просто должна прекратить обработку.
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

    cfg = ws.app.state.settings
    try:
        claims = jwtu.decode_jwt(token, cfg.JWT_SECRET, cfg.JWT_ALG, cfg.JWT_ISS)
    except jwtu.InvalidJWT:
        await ws.close(code=4401)
        return None
    if claims.typ != jwtu.ACCESS:
        await ws.close(code=4401)
        return None

    async with ws.app.state.db_sessionmaker() as session:
        acc = await UserMngr(session).by_id(int(claims.sub))
    if acc is None:
        await ws.close(code=4401)
        return None
    return acc


async def authorize_ws(ws: WebSocket, required_perm: str) -> bool:
    """Дождаться токена и проверить право ``required_perm``.

    При любой неудаче сам закрывает соединение кодом ``4401`` и возвращает
    ``False`` — вызывающая сторона просто должна прекратить обработку.
    """
    acc = await authenticate_ws(ws)
    if acc is None:
        return False
    # Как и в get_current_acc: banned — просто роль, доступ решает has_perm
    # ниже, никакой отдельной проверки role_key тут не делается.
    perms = acc.role.perms if acc.role else None
    if not has_perm(perms, required_perm):
        await ws.close(code=4401)
        return False
    return True


__all__ = ["authenticate_ws", "authorize_ws", "HANDSHAKE_TIMEOUT"]
