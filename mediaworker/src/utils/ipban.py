"""Бан IP в Valkey (защита от фейкового Content-Length при загрузке)."""

from __future__ import annotations

import valkey.asyncio as valkey

_PREFIX = "media:ban:"


async def ban(vk: valkey.Valkey, ip: str, ttl: int) -> None:
    """Забанить IP на ``ttl`` секунд."""
    await vk.set(f"{_PREFIX}{ip}", "1", ex=ttl)


async def is_banned(vk: valkey.Valkey, ip: str) -> bool:
    """Проверить, забанен ли IP."""
    return bool(await vk.exists(f"{_PREFIX}{ip}"))


__all__ = ["ban", "is_banned"]
