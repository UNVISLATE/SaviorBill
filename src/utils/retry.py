"""Политика повторов: счётчик попыток + сигнал исчерпания (для DLQ)."""

from __future__ import annotations

import valkey.asyncio as valkey


async def attempts(vk: valkey.Valkey, key: str, max_attempts: int) -> tuple[int, bool]:
    """Инкремент счётчика попыток. Возвращает (n, исчерпан ли лимит)."""
    n = await vk.incr(f"attempts:{key}")
    return int(n), int(n) >= max_attempts


async def clear_attempts(vk: valkey.Valkey, key: str) -> None:
    """Сбросить счётчик попыток (после успешной обработки)."""
    await vk.delete(f"attempts:{key}")


__all__ = ["attempts", "clear_attempts"]
