"""``GET /apiws/v1/media/mine`` — realtime-статус собственных загрузок (WS).

Раньше карточка каждого файла в обработке опрашивала
``GET /api/media/status/{token}`` по HTTP с интервалом — при нескольких
одновременных загрузках это N параллельных запросов от одного клиента,
плюс задержка отклика самого mediaworker'а, когда он занят конвертацией.

Здесь один WS-канал на пользователя. Первый фрейм от клиента:
``{"token": "<access_jwt>", "watch": ["<media_token>", ...]}`` — ``watch``
обычно это токены, только что полученные из ответа на upload и ещё не
попавшие в основную БД (запись о готовом медиа появляется в ``system_media``
только когда конвертация закончена), поэтому слежение идёт напрямую по
Valkey-статусу (``media:status:{token}``), а не по выборке из БД. Далее в
том же соединении можно присылать ещё ``{"watch": [...]}``, чтобы добавить
токены новых файлов без переоткрытия WS (например, если догрузили ещё).

Сервер сам поллит Valkey (дёшево — ``HGETALL``, без похода в mediaworker по
HTTP) и шлёт клиенту только изменившиеся снимки; как только все токены из
``watch`` дошли до терминального состояния (``ready``/``error``/``failed``)
— отдаёт ``{"type": "idle"}`` и закрывает соединение.

Право доступа — ``user.media.read`` (то же, что для чтения списка своих
медиа по HTTP).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from messaging.mediabus import MediaBus
from models.user import UserMngr
from security.rbac import has_perm, reg_perm
from security.sec import jwt as jwtu

router = APIRouter()

_REQUIRED_PERM = reg_perm("user.media.read")
_POLL_INTERVAL = 1.0
# Защита от бесконечно висящего соединения (напр. клиент не закрыл вкладку,
# а конвертация зависла) — ~10 минут, чего достаточно даже для крупных видео.
_MAX_TICKS = 600
_TERMINAL_STATES = ("ready", "error", "failed")


async def _handshake(ws: WebSocket) -> tuple[int, list[str]] | None:
    """Прочитать первый фрейм, авторизовать и вернуть ``(acc_id, watch[])``.

    При любой неудаче сам закрывает соединение кодом ``4401`` и возвращает
    ``None`` — вызывающая сторона просто должна прекратить обработку.
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=30)
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
    perms = acc.role.perms if acc.role else None
    if not has_perm(perms, _REQUIRED_PERM):
        await ws.close(code=4401)
        return None

    watch = [t for t in (payload.get("watch") or []) if isinstance(t, str)]
    return acc.id, watch


@router.websocket("/media/mine")
async def my_media_status(ws: WebSocket) -> None:
    await ws.accept()
    handshake = await _handshake(ws)
    if handshake is None:
        return
    _acc_id, initial_watch = handshake

    vk = ws.app.state.valkey
    bus = MediaBus(vk)
    watch: set[str] = set(initial_watch)
    last: dict[str, dict] = {}

    try:
        for _ in range(_MAX_TICKS):
            # Короткое окно на приём доп. watch-фреймов между тиками поллинга
            # — не блокирует статус-обновления, просто подмешивает новые
            # токены, если клиент прислал ``{"watch": [...]}`` в это время.
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=_POLL_INTERVAL)
                msg = json.loads(raw)
                for t in msg.get("watch") or []:
                    if isinstance(t, str):
                        watch.add(t)
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            changed: dict[str, dict] = {}
            for token in list(watch):
                snap = await bus.status(token) or {}
                if last.get(token) != snap:
                    changed[token] = snap
                    last[token] = snap
                if snap.get("state") in _TERMINAL_STATES:
                    watch.discard(token)
            if changed:
                await ws.send_json({"type": "status", "items": changed})
            if not watch:
                await ws.send_json({"type": "idle"})
                break
        else:
            await ws.send_json({"type": "timeout"})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


__all__ = ["router"]
