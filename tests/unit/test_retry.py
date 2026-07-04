"""Юнит-тесты utils/retry — счётчик попыток в Valkey."""

from __future__ import annotations

import pytest

from utils.retry import attempts, clear_attempts

pytestmark = pytest.mark.unit


class FakeValkey:
    """Минимальный фейк: INCR + DELETE."""

    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_attempts_increments():
    vk = FakeValkey()
    n, exhausted = await attempts(vk, "job:1", max_attempts=3)
    assert n == 1
    assert exhausted is False


@pytest.mark.asyncio
async def test_attempts_exhausted_at_limit():
    vk = FakeValkey()
    for _ in range(2):
        await attempts(vk, "job:1", max_attempts=3)
    n, exhausted = await attempts(vk, "job:1", max_attempts=3)
    assert n == 3
    assert exhausted is True


@pytest.mark.asyncio
async def test_attempts_beyond_limit():
    """n > max_attempts тоже считается исчерпанным."""
    vk = FakeValkey()
    for _ in range(4):
        n, exhausted = await attempts(vk, "job:1", max_attempts=3)
    assert exhausted is True


@pytest.mark.asyncio
async def test_clear_attempts_resets():
    vk = FakeValkey()
    await attempts(vk, "job:1", max_attempts=3)
    await attempts(vk, "job:1", max_attempts=3)
    await clear_attempts(vk, "job:1")
    n, exhausted = await attempts(vk, "job:1", max_attempts=3)
    assert n == 1
    assert exhausted is False


@pytest.mark.asyncio
async def test_clear_attempts_idempotent():
    """Сброс несуществующего ключа не бросает исключений."""
    vk = FakeValkey()
    await clear_attempts(vk, "nonexistent")  # не должно упасть


@pytest.mark.asyncio
async def test_attempts_independent_keys():
    vk = FakeValkey()
    n1, _ = await attempts(vk, "job:A", max_attempts=2)
    n2, _ = await attempts(vk, "job:B", max_attempts=2)
    assert n1 == 1
    assert n2 == 1
