"""Юнит-тесты бана IP в Valkey (на фейковом клиенте)."""

import utils.ipban as ipban


class FakeVK:
    """Минимальный async-фейк Valkey: set(ex=)/exists."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.last_ex = ex

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0


async def test_not_banned_by_default():
    vk = FakeVK()
    assert await ipban.is_banned(vk, "1.2.3.4") is False


async def test_ban_sets_key_with_ttl():
    vk = FakeVK()
    await ipban.ban(vk, "1.2.3.4", 180)
    assert await ipban.is_banned(vk, "1.2.3.4") is True
    assert vk.last_ex == 180
    assert "media:ban:1.2.3.4" in vk.store


async def test_ban_is_per_ip():
    vk = FakeVK()
    await ipban.ban(vk, "1.1.1.1", 60)
    assert await ipban.is_banned(vk, "2.2.2.2") is False
