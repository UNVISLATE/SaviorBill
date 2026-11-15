"""``GET /api/ws/v1/tasks/{kind}`` — realtime-хвост журнала тасков (WS)."""

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
