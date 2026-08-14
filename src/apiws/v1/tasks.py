"""``GET /api/ws/v1/tasks/{kind}`` — realtime-хвост журнала тасков (WS).

Схема авторизации (per-message, без токена в URL):
1. Клиент открывает соединение без каких-либо auth-параметров.
2. Сервер ``accept()``'ит соединение и даёт ``WS_HANDSHAKE_TIMEOUT_SEC`` секунд
   на присылку токена (см. ``apiws/authctx.py``).
3. Первым текстовым фреймом клиент обязан прислать ``{"token": "<access_jwt>"}``.
4. Если сообщение не пришло вовремя, либо токен невалиден/просрочен, либо у
   аккаунта нет права ``system.tasks.tail.read`` — соединение закрывается кодом
   4401 без утечки данных (бэклог не отправляется). Право отдельное от
   ``system.tasks.summary.read`` — WS-хвост содержит сырой ``detail``/
   ``trace_id`` (см. AUDIT.md §3.6).
5. При успехе — единым сообщением отдаётся бэклог (``TaskLog.tail``), затем
   сервер подписывается на ``tasklog:events:{kind}`` и форвардит новые
   записи клиенту построчно по мере поступления. Параллельно фоновая
   задача (``watch_session``) периодически перепроверяет токен/права и
   закрывает соединение, если они больше не действительны.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from security.rbac import reg_perm

from ..authctx import authorize_ws, watch_session

router = APIRouter()

_KINDS = ("media", "lua")
_REQUIRED_PERM = reg_perm("system.tasks.tail.read")


@router.websocket("/tasks/{kind}")
async def tail_tasks(ws: WebSocket, kind: str) -> None:
    if kind not in _KINDS:
        await ws.close(code=4404)
        return

    await ws.accept()
    result = await authorize_ws(ws, _REQUIRED_PERM)
    if result is None:
        return
    acc, exp = result

    task_log = ws.app.state.task_log
    await ws.send_json({"type": "backlog", "items": await task_log.tail(kind, 100)})

    watchdog = asyncio.create_task(watch_session(ws, acc.id, exp, _REQUIRED_PERM))
    vk = ws.app.state.valkey
    pubsub = vk.pubsub()
    try:
        await pubsub.subscribe(f"tasklog:events:{kind}")
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                await ws.send_text(msg["data"])
            except WebSocketDisconnect:
                break
    finally:
        watchdog.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog
        await pubsub.unsubscribe(f"tasklog:events:{kind}")
        await pubsub.aclose()


__all__ = ["router"]
