"""Шина Python ↔ LuaWorker поверх Redis Streams (Valkey)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

import valkey.asyncio as valkey
from valkey.exceptions import ResponseError

from utils.datetime_utils import timestamp_now

log = logging.getLogger("saviorbill.luabus")


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
        max_retries: int = 0,
        retry_backoff: float = 0,
    ) -> None:
        self.vk = vk
        self.task_stream = task_stream
        self.resp_stream = resp_stream
        self.default_timeout = default_timeout
        # Мягкий таймаут + повторные попытки при таймауте/временной ошибке
        # воркера (см. IMPLEMENTATION_PLAN §9) — изоляция CPU/памяти внутри
        # воркера сознательно оставлена администратору инсталляции.
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    async def _last_id(self) -> str:
        """Текущий конец ответного стрима (база для чтения только новых записей)."""
        try:
            info = await self.vk.xinfo_stream(self.resp_stream)
            return info["last-generated-id"]
        except ResponseError:
            return "0-0"  # стрим ещё не создан

    async def _call_once(
        self, kind: str, payload: dict | None, timeout: int
    ) -> dict:
        """Одна попытка: отправить задачу и дождаться результата."""
        cid = uuid.uuid4().hex
        deadline = timestamp_now() + timeout

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

    async def call(
        self, kind: str, payload: dict | None = None, timeout: int | None = None
    ) -> dict:
        """Отправить задачу и дождаться результата (с ретраями при таймауте).

        :arg kind: тип задачи для воркера.
        :arg payload: произвольная структура данных, прокидывается в Lua.
        :raises LuaError: при ошибке исполнения либо таймауте последней попытки.
        """
        eff_timeout = timeout or self.default_timeout
        attempts = max(1, self.max_retries + 1)
        last_exc: LuaError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self._call_once(kind, payload, eff_timeout)
            except LuaError as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                log.warning(
                    "LuaBus: попытка %s/%s для %r не удалась (%s), повтор через %ss",
                    attempt,
                    attempts,
                    kind,
                    exc,
                    self.retry_backoff,
                )
                if self.retry_backoff:
                    await asyncio.sleep(self.retry_backoff)
        assert last_exc is not None  # attempts >= 1, цикл всегда выполняется
        raise last_exc

    async def submit(self, kind: str, payload: dict | None = None) -> str:
        """Опубликовать задачу без ожидания ответа (fire-and-forget). Возвращает cid."""
        cid = uuid.uuid4().hex
        await self.vk.xadd(
            self.task_stream,
            {"cid": cid, "kind": kind, "payload": json.dumps(payload or {})},
        )
        return cid


__all__ = ["LuaBus", "LuaError"]

