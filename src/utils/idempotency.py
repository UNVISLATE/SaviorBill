"""Утилита идемпотентности: атомарный claim «выполнить ровно один раз».

Ключ ``idem:{key}`` ставится ``SET NX EX`` — первый вызов получает True (можно
выполнять), повторные — False (уже обработано). Освобождение (``release_once``)
нужно, если обработка провалилась и её следует повторить.
"""

from __future__ import annotations

import valkey.asyncio as valkey


async def once(vk: valkey.Valkey, key: str, ttl: int = 86400) -> bool:
    """``SET idem:{key} 1 NX EX ttl``. True = впервые, False = уже обработано."""
    result = await vk.set(f"idem:{key}", "1", nx=True, ex=ttl)
    return bool(result)


async def release_once(vk: valkey.Valkey, key: str) -> None:
    """Снять claim (при ошибке — чтобы разрешить повтор)."""
    await vk.delete(f"idem:{key}")


__all__ = ["once", "release_once"]
