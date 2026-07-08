"""Юнит-тесты анти-брутфорс блокировки логина (`dependencies/login_guard.py`)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from dependencies.login_guard import LoginGuard

pytestmark = pytest.mark.unit


class _FakeValkey:
    """Мини in-memory Valkey: INCR/EXPIRE/MGET/TTL/DELETE без реального TTL."""

    def __init__(self) -> None:
        self._vals: dict[str, int] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._vals[key] = self._vals.get(key, 0) + 1
        return self._vals[key]

    async def expire(self, key: str, ttl: int) -> None:
        self._ttl[key] = ttl

    async def mget(self, keys: list[str]) -> list:
        return [self._vals.get(k) for k in keys]

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, 0)

    async def delete(self, key: str) -> None:
        self._vals.pop(key, None)
        self._ttl.pop(key, None)


class _FakeSettings:
    def __init__(self, max_attempts=5, window_sec=900):
        self.max_attempts = max_attempts
        self.window_sec = window_sec

    async def get_int(self, key, default=None):
        if key == "auth.lockout.max_attempts":
            return self.max_attempts
        if key == "auth.lockout.window_sec":
            return self.window_sec
        return default


@pytest.mark.asyncio
async def test_check_allows_when_under_threshold():
    guard = LoginGuard(_FakeValkey(), _FakeSettings(max_attempts=3))
    await guard.check("alice", "1.2.3.4")  # не бросает


@pytest.mark.asyncio
async def test_record_fail_increments_both_keys():
    vk = _FakeValkey()
    guard = LoginGuard(vk, _FakeSettings(max_attempts=3))
    await guard.record_fail("alice", "1.2.3.4")
    assert vk._vals["login:fail:acc:alice"] == 1
    assert vk._vals["login:fail:ip:1.2.3.4"] == 1


@pytest.mark.asyncio
async def test_check_blocks_after_max_attempts_by_login():
    vk = _FakeValkey()
    guard = LoginGuard(vk, _FakeSettings(max_attempts=2))
    await guard.record_fail("alice", "1.1.1.1")
    await guard.record_fail("alice", "2.2.2.2")  # разные IP, тот же логин
    with pytest.raises(HTTPException) as exc:
        await guard.check("alice", "3.3.3.3")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_check_blocks_after_max_attempts_by_ip():
    vk = _FakeValkey()
    guard = LoginGuard(vk, _FakeSettings(max_attempts=2))
    await guard.record_fail("alice", "9.9.9.9")
    await guard.record_fail("bob", "9.9.9.9")  # разные логины, тот же IP
    with pytest.raises(HTTPException) as exc:
        await guard.check("carol", "9.9.9.9")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_clear_resets_login_but_not_ip_counter():
    vk = _FakeValkey()
    guard = LoginGuard(vk, _FakeSettings(max_attempts=2))
    await guard.record_fail("alice", "5.5.5.5")
    await guard.record_fail("alice", "5.5.5.5")
    await guard.clear("alice")
    # Логин-счётчик сброшен — доступ снова разрешён по логину.
    assert vk._vals.get("login:fail:acc:alice") is None
    # IP-счётчик НЕ сброшен успешным входом (умышленно, см. §6.3 плана).
    assert vk._vals["login:fail:ip:5.5.5.5"] == 2
    with pytest.raises(HTTPException):
        await guard.check("mallory", "5.5.5.5")
