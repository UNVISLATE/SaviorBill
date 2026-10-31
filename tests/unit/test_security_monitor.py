from __future__ import annotations

import json
from unittest.mock import AsyncMock
import pytest

from services.security_monitor import (
    ban_ip,
    check_and_apply_autoban,
    is_ip_banned,
    list_banned_ips,
    list_security_events,
    log_security_event,
    unban_ip,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_log_security_event():
    vk = AsyncMock()
    ev = await log_security_event(
        vk,
        ip="1.2.3.4",
        action="rate_limit_exceeded",
        reason="10 hits/sec",
        scope="api.login",
        kind="auth",
    )
    assert ev["ip"] == "1.2.3.4"
    assert ev["action"] == "rate_limit_exceeded"
    assert vk.lpush.called
    assert vk.ltrim.called


@pytest.mark.asyncio
async def test_ban_and_unban_ip():
    vk = AsyncMock()
    await ban_ip(vk, "1.2.3.4", duration_sec=300, reason="Bad behavior")
    vk.set.assert_called_once()
    vk.sadd.assert_called_once()

    vk.delete.return_value = 1
    unbanned = await unban_ip(vk, "1.2.3.4")
    assert unbanned is True
    vk.srem.assert_called_once()


@pytest.mark.asyncio
async def test_is_ip_banned_true():
    vk = AsyncMock()
    vk.get.return_value = json.dumps({"reason": "Scraping"})
    vk.ttl.return_value = 120

    is_banned, reason, ttl = await is_ip_banned(vk, "1.2.3.4")
    assert is_banned is True
    assert reason == "Scraping"
    assert ttl == 120


@pytest.mark.asyncio
async def test_check_and_apply_autoban():
    vk = AsyncMock()
    # 5-е нарушение при пороге 5
    vk.incr.return_value = 5

    settings = AsyncMock()
    settings.get.side_effect = lambda key, default=None: {
        "security.autoban.enabled": "1",
        "security.autoban.threshold": "5",
        "security.autoban.window_sec": "60",
        "security.autoban.duration_sec": "900",
    }.get(key, default)

    banned = await check_and_apply_autoban(vk, "1.2.3.4", settings)
    assert banned is True
    vk.set.assert_called_once()
