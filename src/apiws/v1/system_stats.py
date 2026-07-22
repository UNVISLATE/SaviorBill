"""``GET /api/ws/v1/system/stats`` — realtime-поток агрегатов инстансов (WS).

Отличие от ``apiws/v1/tasks.py`` (pubsub-хвост событий): здесь **poll по
таймеру**, а не подписка на поток — на каждом тике отдаётся тот же JSON, что
и ``GET /api/v1/system/stats`` (список + агрегаты), НЕ детали конкретного
инстанса (drill-down остаётся отдельным pull-роутом — не смешиваем
summary-право (``system.stats.read``) и instance-право в одном канале).

Схема авторизации — та же, что у ``tasks.py`` (per-message, без токена в URL):
первый текстовый фрейм — ``{"token": "<access_jwt>"}``, дальше клиент может в
любой момент прислать ``{"interval_sec": N}`` (1..``SYSTEM_STATS_WS_MAX_SEC``)
— меняет период поллинга на лету.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import AppConfig
from security.rbac import reg_perm
from telemetry.instance_metrics import list_instances

from ..authctx import authorize_ws

router = APIRouter()

_REQUIRED_PERM = reg_perm("system.stats.read")


async def _read_interval_updates(ws: WebSocket, state: dict, min_sec: int, max_sec: int) -> None:
    """Фоновая корутина: слушать входящие фреймы клиента и обновлять
    ``state["interval_sec"]`` на лету. Невалидные значения/сообщения — тихо
    игнорируются (не рвём поток из-за одного плохого фрейма)."""
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
                interval = float(payload["interval_sec"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if min_sec <= interval <= max_sec:
                state["interval_sec"] = interval
    except WebSocketDisconnect:
        return


@router.websocket("/stats")
async def stream_stats(ws: WebSocket) -> None:
    await ws.accept()
    if not await authorize_ws(ws, _REQUIRED_PERM):
        return

    cfg: AppConfig = ws.app.state.settings
    state = {"interval_sec": cfg.SYSTEM_STATS_WS_DEFAULT_SEC}
    reader = asyncio.create_task(
        _read_interval_updates(ws, state, cfg.SYSTEM_STATS_WS_MIN_SEC, cfg.SYSTEM_STATS_WS_MAX_SEC)
    )
    try:
        while True:
            snapshot = await list_instances(ws.app.state.valkey)
            try:
                await ws.send_json(snapshot)
            except (WebSocketDisconnect, RuntimeError):
                break
            await asyncio.sleep(state["interval_sec"])
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader


__all__ = ["router"]
