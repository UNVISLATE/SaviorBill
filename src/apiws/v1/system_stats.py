"""``GET /api/ws/v1/system/stats`` — realtime-поток агрегатов инстансов (WS).

Отличие от ``apiws/v1/tasks.py`` (pubsub-хвост событий): здесь клиент отдаёт
последний снапшот из общего фонового поллера (``services/stats_broadcaster.py``)
на своём таймере — тот же JSON, что и ``GET /api/v1/system/stats`` (список +
агрегаты), НЕ детали конкретного инстанса (drill-down остаётся отдельным
pull-роутом — не смешиваем summary-право (``system.stats.read``) и
instance-право в одном канале). Один общий поллер вместо запроса в Valkey на
каждого клиента (см. AUDIT.md §3.5) — рост числа подписчиков не увеличивает
нагрузку на Valkey.

Схема авторизации — та же, что у ``tasks.py`` (per-message, без токена в URL):
первый текстовый фрейм — ``{"token": "<access_jwt>"}``, дальше клиент может в
любой момент прислать ``{"interval_sec": N}`` (1..``SYSTEM_STATS_WS_MAX_SEC``)
— меняет частоту, с которой ЕМУ отдаётся кэш (не частоту самого поллинга
Valkey — тот фиксирован, см. ``StatsBroadcaster``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import AppConfig
from security.rbac import reg_perm

from ..authctx import authorize_ws, safe_receive_text, watch_session

router = APIRouter()

_REQUIRED_PERM = reg_perm("system.stats.read")


async def _read_interval_updates(ws: WebSocket, state: dict, min_sec: int, max_sec: int) -> None:
    """Фоновая корутина: слушать входящие фреймы клиента и обновлять
    ``state["interval_sec"]`` на лету. Невалидные значения/сообщения — тихо
    игнорируются (не рвём поток из-за одного плохого фрейма). Бинарные/
    слишком большие фреймы закрывают соединение явно (см. AUDIT.md §3.2/§3.3,
    ``authctx.safe_receive_text``)."""
    while True:
        raw = await safe_receive_text(ws)
        if raw is None:
            return
        try:
            payload = json.loads(raw)
            interval = float(payload["interval_sec"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if min_sec <= interval <= max_sec:
            state["interval_sec"] = interval


@router.websocket("/stats")
async def stream_stats(ws: WebSocket) -> None:
    await ws.accept()
    result = await authorize_ws(ws, _REQUIRED_PERM)
    if result is None:
        return
    acc, exp = result

    cfg: AppConfig = ws.app.state.settings
    state = {"interval_sec": cfg.SYSTEM_STATS_WS_DEFAULT_SEC}
    reader = asyncio.create_task(
        _read_interval_updates(ws, state, cfg.SYSTEM_STATS_WS_MIN_SEC, cfg.SYSTEM_STATS_WS_MAX_SEC)
    )
    watchdog = asyncio.create_task(watch_session(ws, acc.id, exp, _REQUIRED_PERM))
    broadcaster = ws.app.state.stats_broadcaster
    try:
        while True:
            try:
                await ws.send_json(broadcaster.snapshot)
            except (WebSocketDisconnect, RuntimeError):
                break
            await asyncio.sleep(state["interval_sec"])
    finally:
        reader.cancel()
        watchdog.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog


__all__ = ["router"]
