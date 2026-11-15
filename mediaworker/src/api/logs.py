"""Realtime-логи и прогресс ffmpeg — своя привилегия mediaworker."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Security,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials

from utils.authctx import authenticate, authorize
from utils.authws import authorize_ws
from utils.openapi_auth import bearer_scheme
from utils.proclog import ProcLog
from utils.rbac import has_perm

router = APIRouter(prefix="/logs")

_PERM = "system.jobs.read"


async def _require_logs_read(request: Request) -> None:
    acc_id = await authenticate(request)
    perms, _role = await authorize(request, acc_id)
    if not has_perm(perms, _PERM):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"insufficient permissions: {_PERM}")


@router.get("/jobs")
async def recent_jobs(
    request: Request,
    limit: int = 50,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> list[dict]:
    """Последние запуски ffmpeg/ffprobe (job_id + op/token/state/started_at/finished_at)."""
    await _require_logs_read(request)
    proc_log: ProcLog = request.app.state.proc_log
    return await proc_log.recent_jobs(limit)


@router.get("/jobs/{job_id}")
async def job_status(
    request: Request,
    job_id: str,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Метаданные одного запуска (без вывода процесса — см. WS .../tail)."""
    await _require_logs_read(request)
    proc_log: ProcLog = request.app.state.proc_log
    job = await proc_log.get_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


@router.get("/jobs/{job_id}/progress")
async def job_progress(
    request: Request,
    job_id: str,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Одноразовый снимок percent/eta (без live-обновлений — см. WS .../progress/tail).

    Пустой объект — прогресс не публиковался (конвертация изображения — она
    без прогресса, см. ``utils/convert.py``) или TTL job'а истёк.
    """
    await _require_logs_read(request)
    proc_log: ProcLog = request.app.state.proc_log
    return await proc_log.get_progress(job_id)


@router.websocket("/jobs/{job_id}/tail")
async def tail_job_log(ws: WebSocket, job_id: str) -> None:
    """Live сырой вывод job'а (бэклог + форвардинг, как в терминале)."""
    await ws.accept()
    if await authorize_ws(ws, _PERM) is None:
        return

    proc_log: ProcLog = ws.app.state.proc_log
    backlog = await proc_log.tail(job_id)
    await ws.send_json({"type": "backlog", "text": "".join(backlog)})

    vk = ws.app.state.vk
    pubsub = vk.pubsub()
    channel = proc_log.events_channel(job_id)
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


@router.websocket("/jobs/{job_id}/progress/tail")
async def tail_job_progress(ws: WebSocket, job_id: str) -> None:
    """Live percent/eta job'а: снимок при подключении + JSON-события."""
    await ws.accept()
    if await authorize_ws(ws, _PERM) is None:
        return

    proc_log: ProcLog = ws.app.state.proc_log
    snapshot = await proc_log.get_progress(job_id)
    if snapshot:
        await ws.send_json({"type": "snapshot", **snapshot})

    vk = ws.app.state.vk
    pubsub = vk.pubsub()
    channel = proc_log.progress_channel(job_id)
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
