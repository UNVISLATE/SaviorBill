"""Юнит-тесты utils/locks — распределённый лок через SET NX EX."""

from __future__ import annotations

import pytest

from utils.locks import distributed_lock

pytestmark = pytest.mark.unit


class FakeValkey:
    """Минимальный фейк Valkey: SET NX EX + GET + DELETE."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int = 0) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_lock_acquired():
    vk = FakeValkey()
    async with distributed_lock(vk, "mylock") as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_lock_not_double_acquired():
    vk = FakeValkey()
    async with distributed_lock(vk, "mylock"):
        async with distributed_lock(vk, "mylock") as acquired:
            assert acquired is False


@pytest.mark.asyncio
async def test_lock_released_after_context():
    vk = FakeValkey()
    async with distributed_lock(vk, "mylock"):
        pass
    # После выхода из контекста ключ должен быть удалён.
    assert "mylock" not in vk._store


@pytest.mark.asyncio
async def test_lock_not_released_if_expired():
    """Если ключ уже не наш (истёк TTL, перезаписан), мы его не удаляем."""
    vk = FakeValkey()
    async with distributed_lock(vk, "mylock") as acquired:
        assert acquired is True
        # Симулируем истечение TTL: ключ перезаписан чужим токеном.
        vk._store["mylock"] = "alien-token"
    # Чужой токен не должен быть удалён нами.
    assert vk._store.get("mylock") == "alien-token"


@pytest.mark.asyncio
async def test_lock_released_on_exception():
    vk = FakeValkey()
    with pytest.raises(ValueError):
        async with distributed_lock(vk, "mylock"):
            raise ValueError("boom")
    assert "mylock" not in vk._store


@pytest.mark.asyncio
async def test_lock_reacquired_after_release():
    vk = FakeValkey()
    async with distributed_lock(vk, "mylock") as a1:
        assert a1 is True
    async with distributed_lock(vk, "mylock") as a2:
        assert a2 is True
