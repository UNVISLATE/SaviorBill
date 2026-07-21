"""``GET /api/media/mine`` — realtime-статус собственных загрузок (WS).

mediaworker — единственный писатель ``media:status:{token}`` (Valkey), поэтому
роут живёт здесь напрямую, без лишнего сетевого прыжка в billing и обратно
(тот же принцип, что и у ``api/logs.py`` — см. его модуль-докстринг). Раньше
этот WS ошибочно снова оказывался в billing (``apiws/v1/media.py`` там) — см.
IMPLEMENTATION_PLAN.md §3.

Первый фрейм от клиента: ``{"token": "<access_jwt>", "watch": ["<media_token>",
...]}`` — ``watch`` обычно токены, только что полученные из ответа на upload
и ещё не попавшие в основную БД (запись о готовом медиа в billing появляется
только когда конвертация закончена), поэтому слежение идёт напрямую по
Valkey-статусу (``media:status:{token}``), а не по выборке из БД. Далее в
том же соединении можно присылать ещё ``{"watch": [...]}``, чтобы добавить
токены новых файлов без переоткрытия WS.

Авторизация — валидный access-JWT + владение каждым токеном из ``watch``
(``db.media_owner``, тот же read-only доступ к Postgres, что и у HTTP-роутов
mediaworker, см. ``utils/db.py``). Отдельного RBAC-права здесь намеренно нет
(см. IMPLEMENTATION_PLAN.md §3.Б) — доступ к самой загрузке уже gate'ится
правом на upload, читать статус СВОЕЙ же загрузки не отдельная привилегия;
чужие токены в ``watch`` просто тихо игнорируются (не отдают чужой статус).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.authws import authenticate_ws_payload
from utils.keys import status_key

router = APIRouter()

_POLL_INTERVAL = 1.0
# Защита от бесконечно висящего соединения (напр. клиент не закрыл вкладку,
# а конвертация зависла) — ~10 минут, чего достаточно даже для крупных видео.
_MAX_TICKS = 600
_TERMINAL_STATES = ("ready", "error", "failed")


async def _owned_tokens(ws: WebSocket, acc_id: int, tokens: list[str]) -> set[str]:
    """Отфильтровать ``tokens`` до тех, что принадлежат ``acc_id``.

    Пока конвертация не завершена, строки в ``system_media`` (billing) ещё
    нет — её создаёт ``media_results`` consumer только по готовому результату
    (см. ``src/services/media_results.py``). Из-за этого владение свежих,
    ещё обрабатывающихся токенов раньше не подтверждалось вообще: WS сразу
    решал, что следить не за чем, и закрывался — прогресс/ETA никогда не
    доходили до клиента. Поэтому при отсутствии записи в БД проверяем
    ``owner_id``, который сам mediaworker пишет в статус-хэш при приёме
    файла (см. ``api/upload.py``).
    """
    if not tokens:
        return set()
    db = ws.app.state.db
    vk = ws.app.state.vk
    owned: set[str] = set()
    for token in tokens:
        media = await db.media_owner(token)
        if media is not None:
            if media[1] == acc_id:
                owned.add(token)
            continue
        owner_raw = await vk.hget(status_key(token), "owner_id")
        if owner_raw is not None:
            owner_str = owner_raw.decode() if isinstance(owner_raw, bytes) else owner_raw
            if owner_str and owner_str == str(acc_id):
                owned.add(token)
    return owned


@router.websocket("/mine")
async def my_media_status(ws: WebSocket) -> None:
    await ws.accept()
    handshake = await authenticate_ws_payload(ws)
    if handshake is None:
        return
    acc_id, payload = handshake

    initial_watch = [t for t in (payload.get("watch") or []) if isinstance(t, str)]
    watch = await _owned_tokens(ws, acc_id, initial_watch)

    vk = ws.app.state.vk
    last: dict[str, dict] = {}

    try:
        for _ in range(_MAX_TICKS):
            # Короткое окно на приём доп. watch-фреймов между тиками поллинга
            # — не блокирует статус-обновления, просто подмешивает новые
            # токены, если клиент прислал ``{"watch": [...]}`` в это время.
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=_POLL_INTERVAL)
                msg = json.loads(raw)
                new_tokens = [t for t in (msg.get("watch") or []) if isinstance(t, str)]
                watch |= await _owned_tokens(ws, acc_id, new_tokens)
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            changed: dict[str, dict] = {}
            for token in list(watch):
                snap = await vk.hgetall(status_key(token)) or {}
                if last.get(token) != snap:
                    # owner_id — служебное поле только для проверки прав
                    # (см. _owned_tokens), клиенту показывать не нужно.
                    changed[token] = {k: v for k, v in snap.items() if k != "owner_id"}
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
