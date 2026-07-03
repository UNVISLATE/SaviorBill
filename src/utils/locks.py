"""Распределённые локи для координации инстансов.

``distributed_lock`` — контекст-менеджер поверх ``SET NX EX``. Значение — уникальный
токен; освобождение в ``finally`` только если лок всё ещё наш (защита от снятия
чужого лока после истечения TTL).
"""

from __future__ import annotations

import contextlib
import uuid

import valkey.asyncio as valkey


@contextlib.asynccontextmanager
async def distributed_lock(vk: valkey.Valkey, key: str, ttl: int = 60):
    """Распределённый лок через ``SET NX EX``.

    Отдаёт True, если лок захвачен, иначе False. Освобождает в ``finally`` только
    собственный токен.
    """
    token = uuid.uuid4().hex
    acquired = bool(await vk.set(key, token, nx=True, ex=ttl))
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        cur = await vk.get(key)
        val = cur.decode() if isinstance(cur, bytes) else cur
        if val == token:
            await vk.delete(key)


__all__ = ["distributed_lock"]
