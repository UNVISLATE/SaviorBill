"""Шина Python <-> LuaWorker поверх Redis Streams (Valkey).

Python публикует задачу в ``task_stream`` (XADD), LuaWorker исполняет её и
кладёт результат в ``resp_stream``. Ответ сопоставляется с задачей по ``cid``.
Чтение ответного стрима неблокирующее для других ожидающих: используется
обычный XREAD (без consumer-групп), поэтому waiter'ы не «воруют» чужие записи.
"""

from __future__ import annotations

import json
import uuid

import valkey.asyncio as valkey
from valkey.exceptions import ResponseError

from utils.datetime_utils import timestamp_now


class LuaError(RuntimeError):
    """LuaWorker вернул ошибку или не ответил вовремя."""


class LuaBus:
    """Клиент шины задач для LuaWorker."""

    def __init__(
        self,
        vk: valkey.Valkey,
        task_stream: str,
        resp_stream: str,
        default_timeout: int = 30,
    ) -> None:
        self.vk = vk
        self.task_stream = task_stream
        self.resp_stream = resp_stream
        self.default_timeout = default_timeout

    async def _last_id(self) -> str:
        """Текущий конец ответного стрима (база для чтения только новых записей)."""
        try:
            info = await self.vk.xinfo_stream(self.resp_stream)
            return info["last-generated-id"]
        except ResponseError:
            return "0-0"  # стрим ещё не создан

    async def call(
        self, kind: str, payload: dict | None = None, timeout: int | None = None
    ) -> dict:
        """Отправить задачу и дождаться результата.

        :param kind: тип задачи для воркера (``http`` / ``billing`` / ``eval`` / ...).
        :param payload: произвольная структура данных, прокидывается в Lua.
        :raises LuaError: при ошибке исполнения или таймауте.
        """
        cid = uuid.uuid4().hex
        deadline = timestamp_now() + (timeout or self.default_timeout)

        last = await self._last_id()
        await self.vk.xadd(
            self.task_stream,
            {"cid": cid, "kind": kind, "payload": json.dumps(payload or {})},
        )

        while True:
            remain = deadline - timestamp_now()
            if remain <= 0:
                raise LuaError(f"таймаут ожидания ответа LuaWorker (cid={cid})")

            res = await self.vk.xread(
                {self.resp_stream: last}, block=min(remain, 5) * 1000, count=20
            )
            for _stream, entries in res or []:
                for entry_id, fields in entries:
                    last = entry_id
                    if fields.get("cid") != cid:
                        continue
                    data = json.loads(fields.get("data") or "null")
                    if fields.get("ok") == "1":
                        return data if isinstance(data, dict) else {"result": data}
                    raise LuaError(str(data))

    async def submit(self, kind: str, payload: dict | None = None) -> str:
        """Опубликовать задачу без ожидания ответа (fire-and-forget). Возвращает cid."""
        cid = uuid.uuid4().hex
        await self.vk.xadd(
            self.task_stream,
            {"cid": cid, "kind": kind, "payload": json.dumps(payload or {})},
        )
        return cid


__all__ = ["LuaBus", "LuaError"]
