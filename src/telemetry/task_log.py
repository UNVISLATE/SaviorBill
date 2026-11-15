"""Журнал задач воркеров в Valkey Streams."""

from __future__ import annotations

import json
import time
from typing import Any

import valkey.asyncio as valkey

from telemetry.otel import current_trace_id

_PREFIX = "tasklog:"
_EVENTS_PREFIX = "tasklog:events:"


class TaskLog:
    """Журнал фактов о тасках одного вида (``kind``: ``"lua"``/``"media"``)."""

    def __init__(
        self,
        vk: valkey.Valkey,
        max_len: int = 500,
        ttl: int = 604_800,
        sm: Any = None,
    ) -> None:
        self.vk = vk
        self.max_len = max_len
        self.ttl = ttl
        self.sm = sm

    async def record(
        self,
        *,
        kind: str,
        op: str,
        token_or_cid: str,
        state: str,
        detail: str | None = None,
        meta: dict | None = None,
    ) -> None:
        """Добавить факт в кольцевой буфер + опубликовать событие для WS."""
        entry = {
            "ts": time.time(),
            "kind": kind,
            "op": op,
            "token_or_cid": token_or_cid,
            "state": state,
            "detail": detail,
            "meta": meta,
            # None, если OTEL выключен — журнал работает независимо от
            # трейсинга, trace_id только для сшивки при необходимости.
            "trace_id": current_trace_id(),
        }
        raw = json.dumps(entry, ensure_ascii=False)
        key = f"{_PREFIX}{kind}"
        await self.vk.lpush(key, raw)
        await self.vk.ltrim(key, 0, self.max_len - 1)
        await self.vk.expire(key, self.ttl)
        await self.vk.publish(f"{_EVENTS_PREFIX}{kind}", raw)

        if self.sm is not None and state in ("ok", "error", "done", "failed"):
            try:
                dur = meta.get("duration_ms") if meta else None
                async with self.sm() as session:
                    from models.task_archive import TaskArchiveMngr

                    arch = TaskArchiveMngr(session)
                    await arch.record(
                        task_id=token_or_cid,
                        kind=kind,
                        operation=op,
                        status="success" if state in ("ok", "done") else "failed",
                        duration_ms=dur,
                        error_message=detail if state == "error" else None,
                        meta=meta,
                    )
                    await session.commit()
            except Exception:
                pass

    async def tail(self, kind: str, limit: int = 100) -> list[dict]:
        """Последние ``limit`` фактов (от новых к старым), включая ``detail``/
        ``trace_id`` — для права ``system.tasks.tail.read`` (сырая диагностика,
)."""
        raw = await self.vk.lrange(f"{_PREFIX}{kind}", 0, limit - 1)
        out: list[dict] = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except (TypeError, ValueError):
                continue
        return out

    async def tail_summary(self, kind: str, limit: int = 100) -> list[dict]:
        """Те же факты, но без ``detail``/``trace_id`` — для права
        ``system.tasks.summary.read`` (кто/что/когда, без внутренней
        диагностики ошибок)."""
        return [_sanitize(entry) for entry in await self.tail(kind, limit)]


def _sanitize(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in ("detail", "trace_id")}


__all__ = ["TaskLog"]
