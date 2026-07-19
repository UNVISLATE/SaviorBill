"""``/apiws/v1/logs/media/{job_id}`` — realtime сырой вывод ffmpeg/ffprobe,
и ``/apiws/v1/logs/media/{job_id}/progress`` — realtime процент/ETA.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from telemetry import proclog_read
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


@router.websocket("/logs/media/{job_id}/progress")
async def tail_media_progress(ws: WebSocket, job_id: str) -> None:
    """Отдельный от сырого лога канал: структурированный JSON-снимок
    (percent/eta_sec/fps/speed), а не текст терминала — см. ``proclog.py``.
    """
    await ws.accept()
    if not await authorize_ws(ws, _REQUIRED_PERM):
        return

    vk = ws.app.state.valkey
    snapshot = await proclog_read.get_progress(vk, job_id)
    if snapshot:
        await ws.send_json({"type": "snapshot", **snapshot})

    pubsub = vk.pubsub()
    channel = proclog_read.progress_channel(job_id)
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
