"""Юнит-тесты rate limiter (sliding window log поверх Valkey)."""

import pytest

from security.ratelimit import LimitRule, RateLimiter

pytestmark = pytest.mark.unit


class FakeValkey:
    """Фейк Valkey: исполняет тот же sliding-window-log, что и Lua-скрипт.

    Хранит на каждый ключ список ``(score_ms, member)`` и повторяет семантику
    ``ZREMRANGEBYSCORE`` → ``ZCARD`` → решение → ``ZADD``.
    """

    def __init__(self) -> None:
        self.z: dict[str, list[tuple[int, str]]] = {}

    async def eval(self, script, numkeys, key, now, window, limit, member):
        now, window, limit = int(now), int(window), int(limit)
        bucket = self.z.setdefault(key, [])
        # ZREMRANGEBYSCORE key 0 (now-window): выкинуть всё <= now-window
        bucket[:] = [(s, m) for (s, m) in bucket if s > now - window]
        count = len(bucket)
        if count < limit:
            bucket.append((now, member))
            return [1, limit - count - 1, 0]
        oldest = min(s for s, _ in bucket)
        retry = max((oldest + window) - now, 0)
        return [0, 0, retry]


@pytest.mark.asyncio
async def test_allows_within_limit():
    rl = RateLimiter(FakeValkey(), now_ms=lambda: 0)
    rule = LimitRule(max_hits=3, window=60)
    res = await rl.hit("auth.login", "1.2.3.4", rule)
    assert res.allowed is True
    assert res.remaining == 2
    assert res.retry_after == 0


@pytest.mark.asyncio
async def test_blocks_over_limit():
    clock = {"t": 0}
    rl = RateLimiter(FakeValkey(), now_ms=lambda: clock["t"])
    rule = LimitRule(max_hits=2, window=30)
    last = None
    for _ in range(3):
        last = await rl.hit("auth.login", "ip", rule)
    assert last.allowed is False
    assert last.remaining == 0
    assert last.retry_after == 30


@pytest.mark.asyncio
async def test_window_slides_after_expiry():
    clock = {"t": 0}
    rl = RateLimiter(FakeValkey(), now_ms=lambda: clock["t"])
    rule = LimitRule(max_hits=1, window=10)
    assert (await rl.hit("s", "id", rule)).allowed is True
    assert (await rl.hit("s", "id", rule)).allowed is False
    # Спустя полное окно метка устаревает — снова разрешено.
    clock["t"] = 10_001
    assert (await rl.hit("s", "id", rule)).allowed is True


@pytest.mark.asyncio
async def test_no_double_at_window_boundary():
    """Ключевая проверка: на стыке окон лимит НЕ удваивается.

    Фиксированное окно позволило бы 2 в конце окна и ещё 2 в начале следующего.
    Скользящее окно учитывает обе метки конца предыдущего окна.
    """
    clock = {"t": 0}
    rl = RateLimiter(FakeValkey(), now_ms=lambda: clock["t"])
    rule = LimitRule(max_hits=2, window=1)  # 1000 мс

    clock["t"] = 999
    assert (await rl.hit("s", "id", rule)).allowed is True  # 1/2
    assert (await rl.hit("s", "id", rule)).allowed is True  # 2/2

    # «Начало следующего фиксированного окна» — но обе метки ещё в скольжении.
    clock["t"] = 1000
    res = await rl.hit("s", "id", rule)
    assert res.allowed is False  # не даём удвоить лимит


@pytest.mark.asyncio
async def test_separate_idents_independent():
    rl = RateLimiter(FakeValkey(), now_ms=lambda: 0)
    rule = LimitRule(max_hits=1, window=60)
    a = await rl.hit("scope", "a", rule)
    b = await rl.hit("scope", "b", rule)
    assert a.allowed is True
    assert b.allowed is True
