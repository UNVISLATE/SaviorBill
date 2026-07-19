"""``/apiws/v1/logs/media/{job_id}`` — realtime сырой вывод ffmpeg/ffprobe"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils import proclog_read
from security.rbac import reg_perm

from ...authctx import authorize_ws

router = APIRouter()

_REQUIRED_PERM = reg_perm("logs.read")


@router.websocket("/logs/media/{job_id}")
async def tail_media_log(ws: WebSocket, job_id: str) -> None:
    await ws.accept()
    if not await authorize_ws(ws, _REQUIRED_PERM):
        return

    vk = ws.app.state.valkey
    backlog = await proclog_read.tail(vk, job_id)
    await ws.send_json({"type": "backlog", "text": "".join(backlog)})

    pubsub = vk.pubsub()
    channel = proclog_read.events_channel(job_id)
    try:
        await pubsub.subscribe(channel)
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                await ws.send_text(msg["data"])
            except WebSocketDisconnect:
                break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


__all__ = ["router"]
