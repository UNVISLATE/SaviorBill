"""Юнит-тесты SettingsResolver: квоты общего объёма (media.quota.*)."""

from types import SimpleNamespace

from utils.settings import SettingsResolver


class _FakeVk:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


class _FakeDB:
    def __init__(self, settings: dict[str, str] | None = None):
        self.settings = settings or {}

    async def setting(self, key):
        return self.settings.get(key)


def _cfg(**overrides):
    base = dict(quota_image_bytes=52_428_800, quota_video_bytes=2_147_483_648)
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_quota_image_bytes_falls_back_to_config_default():
    resolver = SettingsResolver(_cfg(), _FakeVk(), _FakeDB())
    assert await resolver.quota_image_bytes() == 52_428_800


async def test_quota_video_bytes_reads_from_db_when_set():
    db = _FakeDB({"media.quota.video_bytes": "999"})
    resolver = SettingsResolver(_cfg(), _FakeVk(), db)
    assert await resolver.quota_video_bytes() == 999


async def test_quota_image_bytes_prefers_valkey_cache_over_db():
    vk = _FakeVk()
    vk.store["settings:media.quota.image_bytes"] = "123"
    db = _FakeDB({"media.quota.image_bytes": "456"})
    resolver = SettingsResolver(_cfg(), vk, db)
    assert await resolver.quota_image_bytes() == 123
