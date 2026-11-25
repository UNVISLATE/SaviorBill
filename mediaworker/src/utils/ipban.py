"""Бан IP в Valkey (защита от фейкового Content-Length при загрузке)."""

from __future__ import annotations

import valkey.asyncio as valkey

_PREFIX = "media:ban:"
_SHARED_BAN_PREFIX = "security:banned_ips:"


async def ban(vk: valkey.Valkey, ip: str, ttl: int) -> None:
    """Забанить IP на ``ttl`` секунд."""
    await vk.set(f"{_PREFIX}{ip}", "1", ex=ttl)


async def is_banned(vk: valkey.Valkey, ip: str) -> bool:
    """Проверить, забанен ли IP (локально в mediaworker или глобально в billing)."""
    if await vk.exists(f"{_PREFIX}{ip}"):
        return True
    return bool(await vk.exists(f"{_SHARED_BAN_PREFIX}{ip}"))


__all__ = ["ban", "is_banned"]
