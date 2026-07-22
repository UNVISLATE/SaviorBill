"""``GET /api/ws/v1/tasks/{kind}`` — realtime-хвост журнала тасков (WS).

Схема авторизации (per-message, без токена в URL):
1. Клиент открывает соединение без каких-либо auth-параметров.
2. Сервер ``accept()``'ит соединение и даёт 30 секунд на присылку токена.
3. Первым текстовым фреймом клиент обязан прислать ``{"token": "<access_jwt>"}``.
4. Если сообщение не пришло за 30с, либо токен невалиден/просрочен, либо у
   аккаунта нет права ``system.tasks.read`` — соединение закрывается кодом
   4401 без утечки данных (бэклог не отправляется).
5. При успехе — единым сообщением отдаётся бэклог (``TaskLog.tail``), затем
   сервер подписывается на ``tasklog:events:{kind}`` и форвардит новые
   записи клиенту построчно по мере поступления.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from security.rbac import reg_perm

from ..authctx import authorize_ws

router = APIRouter()

_KINDS = ("media", "lua")
_REQUIRED_PERM = reg_perm("system.tasks.read")


@router.websocket("/tasks/{kind}")
async def tail_tasks(ws: WebSocket, kind: str) -> None:
    if kind not in _KINDS:
        await ws.close(code=4404)
        return

    await ws.accept()
    if not await authorize_ws(ws, _REQUIRED_PERM):
        return

    task_log = ws.app.state.task_log
    await ws.send_json({"type": "backlog", "items": await task_log.tail(kind, 100)})

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
        await pubsub.unsubscribe(f"tasklog:events:{kind}")
        await pubsub.aclose()


__all__ = ["router"]
