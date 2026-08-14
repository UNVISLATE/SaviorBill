"""Общая логика авторизации WS-хендшейка для ``/api/ws/*`` (без токена в URL)"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import WebSocket, WebSocketDisconnect
from starlette import status as ws_status

from models.user import UserMngr, UserModel
from security.rbac import has_perm
from security.sec import jwt as jwtu
from utils.degrade import VALKEY_ERRORS, note_degraded

# Периодичность повторной проверки токена/прав уже открытого соединения
# (см. ``watch_session`` / AUDIT.md §3.4).
REAUTH_INTERVAL_SEC = 30

_PREAUTH_PREFIX = "ws:preauth:"


def _handshake_timeout(ws: WebSocket) -> int:
    """Окно ожидания первого фрейма с токеном — берётся из конфига
    (``WS_HANDSHAKE_TIMEOUT_SEC``), а не хардкодится, чтобы значение можно
    было менять окружением без правки кода (см. AUDIT.md §3.1)."""
    cfg = ws.app.state.settings
    return cfg.WS_HANDSHAKE_TIMEOUT_SEC


async def _acquire_preauth_slot(ws: WebSocket) -> bool:
    """Ограничить число одновременных pre-auth-соединений на IP (Valkey-счётчик
    с TTL = окно хендшейка) — без этого открыть много сокетов и не слать токен
    было тривиальным resource exhaustion (см. AUDIT.md §3.1).

    При недоступности Valkey — пропускаем (лимит вспомогательный, отказ в
    обслуживании хуже отсутствия лимита, см. utils/degrade.py).
    """
    cfg = ws.app.state.settings
    vk = ws.app.state.valkey
    ip = ws.client.host if ws.client else "unknown"
    key = f"{_PREAUTH_PREFIX}{ip}"
    try:
        count = await vk.incr(key)
        if count == 1:
            await vk.expire(key, _handshake_timeout(ws) + 5)
        if count > cfg.WS_PREAUTH_MAX_PER_IP:
            await vk.decr(key)
            return False
    except VALKEY_ERRORS as exc:
        note_degraded("ws_preauth_limit", exc)
    return True


async def _release_preauth_slot(ws: WebSocket) -> None:
    vk = ws.app.state.valkey
    ip = ws.client.host if ws.client else "unknown"
    try:
        await vk.decr(f"{_PREAUTH_PREFIX}{ip}")
    except VALKEY_ERRORS as exc:
        note_degraded("ws_preauth_limit", exc)


async def safe_receive_text(ws: WebSocket, *, timeout: float | None = None) -> str | None:
    """Прочитать один текстовый фрейм с явной обработкой бинарных/слишком
    больших сообщений — общий читатель для хендшейка и последующих фреймов
    уже открытого соединения (см. AUDIT.md §3.2/§3.3).

    :return: текст фрейма, либо ``None`` — соединение уже закрыто данной
        функцией (таймаут/disconnect/binary/too-big), вызывающая сторона
        должна прекратить обработку.
    """
    cfg = ws.app.state.settings
    try:
        if timeout is not None:
            message = await asyncio.wait_for(ws.receive(), timeout=timeout)
        else:
            message = await ws.receive()
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=4401)
        return None

    if message.get("type") == "websocket.disconnect":
        return None

    if "bytes" in message and message["bytes"] is not None:
        # Бинарные фреймы не поддерживаются протоколом — закрываем явно,
        # вместо необработанного исключения на попытке прочитать "text".
        await ws.close(code=ws_status.WS_1003_UNSUPPORTED_DATA)
        return None

    raw = message.get("text")
    if raw is None:
        await ws.close(code=4401)
        return None

    if len(raw.encode("utf-8", errors="ignore")) > cfg.WS_MAX_FRAME_BYTES:
        await ws.close(code=ws_status.WS_1009_MESSAGE_TOO_BIG)
        return None
    return raw


async def _recv_handshake_frame(ws: WebSocket) -> str | None:
    """Дождаться первого фрейма хендшейка (с таймаутом) — см. :func:`safe_receive_text`."""
    return await safe_receive_text(ws, timeout=_handshake_timeout(ws))


async def authenticate_ws(ws: WebSocket) -> tuple[UserModel, int] | None:
    """Дождаться первого фрейма с токеном и вернуть (аккаунт, exp токена).

    При любой неудаче сам закрывает соединение и возвращает ``None`` —
    вызывающая сторона просто должна прекратить обработку.
    """
    if not await _acquire_preauth_slot(ws):
        await ws.close(code=ws_status.WS_1013_TRY_AGAIN_LATER)
        return None
    try:
        raw = await _recv_handshake_frame(ws)
        if raw is None:
            return None

        try:
            payload = json.loads(raw)
            token = payload["token"]
        except (json.JSONDecodeError, KeyError, TypeError):
            await ws.close(code=4401)
            return None

        cfg = ws.app.state.settings
        try:
            claims = jwtu.decode_jwt(token, cfg.jwt_public_keys(), cfg.JWT_ALG, cfg.JWT_ISS)
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
        return acc, int(claims.exp)
    finally:
        await _release_preauth_slot(ws)


async def authorize_ws(ws: WebSocket, required_perm: str) -> tuple[UserModel, int] | None:
    """Дождаться токена и проверить право ``required_perm``.

    При любой неудаче сам закрывает соединение кодом ``4401`` и возвращает
    ``None`` — вызывающая сторона просто должна прекратить обработку.
    """
    result = await authenticate_ws(ws)
    if result is None:
        return None
    acc, exp = result
    # Как и в get_current_acc: banned — просто роль, доступ решает has_perm
    # ниже, никакой отдельной проверки role_key тут не делается.
    perms = acc.role.perms if acc.role else None
    if not has_perm(perms, required_perm):
        await ws.close(code=4401)
        return None
    return acc, exp


async def watch_session(
    ws: WebSocket, acc_id: int, exp: int, required_perm: str
) -> None:
    """Фоновая задача: пока соединение живо, периодически перепроверять, что
    токен ещё не истёк и право не отозвано.

    Единственная проверка на хендшейке означала, что соединение жило
    неограниченно долго после неё — истечение токена или отзыв права не
    разрывали уже открытый WS (TOCTOU, см. AUDIT.md §3.4). Запускается как
    отдельная задача рядом с основным циклом роута; при провале сама
    закрывает сокет, что рвёт основной цикл через ``WebSocketDisconnect``.
    """
    try:
        while True:
            await asyncio.sleep(REAUTH_INTERVAL_SEC)
            if time.time() >= exp:
                await ws.close(code=4401)
                return
            async with ws.app.state.db_sessionmaker() as session:
                acc = await UserMngr(session).by_id(acc_id)
            if acc is None:
                await ws.close(code=4401)
                return
            perms = acc.role.perms if acc.role else None
            if not has_perm(perms, required_perm):
                await ws.close(code=4401)
                return
    except (WebSocketDisconnect, RuntimeError):
        return


__all__ = [
    "authenticate_ws",
    "authorize_ws",
    "watch_session",
    "safe_receive_text",
    "REAUTH_INTERVAL_SEC",
]
