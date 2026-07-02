"""Бан IP в Valkey (короткоживущий) для защиты от абьюза загрузки.

Бан ставится ТОЛЬКО когда клиент обманул размер (фейковый Content-Length и
фактическая передача больше разрешённого объёма). Сам по себе большой
Content-Length — честный отказ 413 без бана.
"""

from __future__ import annotations

import valkey.asyncio as valkey

_PREFIX = "media:ban:"


async def ban(vk: valkey.Valkey, ip: str, ttl: int) -> None:
    """Забанить IP на ``ttl`` секунд.

    :arg vk: клиент Valkey.
    :arg ip: адрес клиента.
    :arg ttl: длительность бана в секундах.
    """
    if ip:
        await vk.set(f"{_PREFIX}{ip}", "1", ex=ttl)


async def is_banned(vk: valkey.Valkey, ip: str) -> bool:
    """Проверить, забанен ли IP.

    :arg vk: клиент Valkey.
    :arg ip: адрес клиента.
    :return: ``True`` если бан активен.
    """
    if not ip:
        return False
    return bool(await vk.exists(f"{_PREFIX}{ip}"))


__all__ = ["ban", "is_banned"]
