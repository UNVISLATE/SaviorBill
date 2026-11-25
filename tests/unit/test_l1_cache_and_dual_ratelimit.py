"""Юнит-тесты L1-кэша настроек и dual-window rate limiter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.system_settings import SystemSettingsMngr, _L1_CACHE
from security.ratelimit import LimitRule, RateLimiter

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_settings_l1_caches_hot_prefixes_and_skips_critical() -> None:
    vk = MagicMock()
    vk.get = AsyncMock(side_effect=["1", "code", "authenticated"])
    vk.set = AsyncMock()
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    box = SimpleNamespace(open=lambda v: v, seal=lambda v: v)

    _L1_CACHE.clear()
    mngr = SystemSettingsMngr(session, vk, box, cache_ttl=300)

    # 1. Hot prefix "catalog.*" -> cached in L1 after 1st read
    assert await mngr.get("catalog.cache.enabled") == "1"
    assert await mngr.get("catalog.cache.enabled") == "1"
    assert vk.get.call_count == 1

    # 2. set() invalidates L1 immediately
    await mngr.set("catalog.cache.enabled", "0")
    assert (id(vk), "catalog.cache.enabled") not in _L1_CACHE

    # 3. Critical prefix "password.*" -> NOT cached in L1, always reads Valkey
    assert await mngr.get("password.reset.method") == "code"
    assert await mngr.get("password.reset.method") == "authenticated"
    assert vk.get.call_count == 3


@pytest.mark.asyncio
async def test_rate_limiter_hit_dual_parses_burst_and_main() -> None:
    vk = MagicMock()
    vk.eval = AsyncMock(
        side_effect=[
            [1, 9, 0, 0],   # allowed
            [0, 0, 1000, 1],  # burst violation
            [0, 0, 5000, 2],  # main window violation
        ]
    )
    limiter = RateLimiter(vk, now_ms=lambda: 1000000)
    burst = LimitRule(3, 1)
    main = LimitRule(10, 60)

    res1, is_burst1 = await limiter.hit_dual("s:burst", "s", "ip:1.1.1.1", burst, main)
    assert res1.allowed is True and res1.remaining == 9 and is_burst1 is False

    res2, is_burst2 = await limiter.hit_dual("s:burst", "s", "ip:1.1.1.1", burst, main)
    assert res2.allowed is False and res2.retry_after == 1 and is_burst2 is True

    res3, is_burst3 = await limiter.hit_dual("s:burst", "s", "ip:1.1.1.1", burst, main)
    assert res3.allowed is False and res3.retry_after == 5 and is_burst3 is False
