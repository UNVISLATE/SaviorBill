"""Юнит-тесты utils/ipban — бан IP в Valkey."""

from __future__ import annotations

import pytest

from utils.ipban import ban, is_banned

pytestmark = pytest.mark.unit


class FakeValkey:
    """Минимальный фейк: SET с TTL + EXISTS."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int = 0) -> None:
        self._store[key] = value

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.mark.asyncio
async def test_ban_and_is_banned():
    vk = FakeValkey()
    await ban(vk, "1.2.3.4", ttl=60)
    assert await is_banned(vk, "1.2.3.4") is True


@pytest.mark.asyncio
async def test_not_banned_initially():
    vk = FakeValkey()
    assert await is_banned(vk, "5.6.7.8") is False


@pytest.mark.asyncio
async def test_ban_empty_ip_noop():
    """Пустой IP не должен банить ничего."""
    vk = FakeValkey()
    await ban(vk, "", ttl=60)
    assert len(vk._store) == 0


@pytest.mark.asyncio
async def test_is_banned_empty_ip_returns_false():
    """Пустой IP не должен считаться забаненным."""
    vk = FakeValkey()
    assert await is_banned(vk, "") is False


@pytest.mark.asyncio
async def test_ban_stores_correct_key():
    vk = FakeValkey()
    await ban(vk, "10.0.0.1", ttl=30)
    assert "media:ban:10.0.0.1" in vk._store


@pytest.mark.asyncio
async def test_different_ips_independent():
    vk = FakeValkey()
    await ban(vk, "1.1.1.1", ttl=60)
    assert await is_banned(vk, "1.1.1.1") is True
    assert await is_banned(vk, "2.2.2.2") is False


@pytest.mark.asyncio
async def test_unban_clears_ban():
    vk = FakeValkey()
    await ban(vk, "9.9.9.9", ttl=60)
    await vk.delete("media:ban:9.9.9.9")
    assert await is_banned(vk, "9.9.9.9") is False
