"""Ограничение частоты запросов (sliding window) поверх Valkey."""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import ceil
from secrets import token_hex
from typing import Callable

import valkey.asyncio as valkey


@dataclass(frozen=True)
class LimitRule:
    """Правило лимита: не более ``max_hits`` обращений за ``window`` секунд."""

    max_hits: int
    window: int


@dataclass(frozen=True)
class LimitResult:
    """Результат проверки лимита."""

    allowed: bool
    remaining: int
    retry_after: int  # секунд до освобождения слота (0, если разрешено)


# Префикс ключей лимитов в Valkey.
_PREFIX = "rl:"

# Атомарный sliding-window-log на ZSET.
#   KEYS[1]            — ключ окна
#   ARGV[1] now        — текущее время, мс
#   ARGV[2] window     — размер окна, мс
#   ARGV[3] limit      — максимум обращений в окне
#   ARGV[4] member     — уникальная метка обращения (now:rand)
# Возвращает {allowed, remaining, retry_after_ms}.
_SCRIPT = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window)
    return {1, limit - count - 1, 0}
end

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry = window
if oldest[2] then
    retry = (tonumber(oldest[2]) + window) - now
    if retry < 0 then retry = 0 end
end
redis.call('PEXPIRE', key, window)
return {0, 0, retry}
"""


class RateLimiter:
    """Скользящее окно частоты обращений поверх Valkey (ZSET + Lua)."""

    def __init__(
        self, vk: valkey.Valkey, now_ms: Callable[[], int] | None = None
    ) -> None:
        self.vk = vk
        self._now = now_ms or (lambda: int(time.time() * 1000))

    async def hit(self, scope: str, ident: str, rule: LimitRule) -> LimitResult:
        """Зарегистрировать обращение и вернуть вердикт.

        :arg scope: логическое имя точки (``auth.login``, ``mail.verify`` …).
        :arg ident: идентификатор клиента (IP или метка токена).
        :arg rule:  правило лимита.
        """
        key = f"{_PREFIX}{scope}:{ident}"
        now = self._now()
        member = f"{now}:{token_hex(8)}"
        raw = await self.vk.eval(
            _SCRIPT,
            1,
            key,
            now,
            rule.window * 1000,
            rule.max_hits,
            member,
        )
        allowed, remaining, retry_ms = (int(raw[0]), int(raw[1]), int(raw[2]))
        return LimitResult(
            allowed=bool(allowed),
            remaining=remaining,
            retry_after=ceil(retry_ms / 1000) if retry_ms > 0 else 0,
        )


__all__ = ["LimitRule", "LimitResult", "RateLimiter"]
