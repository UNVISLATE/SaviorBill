"""Юнит-тесты ProcLog.set_progress — сериализация полей в Valkey hash.

Регрессия: ``done`` (bool) падал с DataError при передаче как есть в
``hset(mapping=...)`` — valkey-клиент принимает только bytes/str/int/float.
Ошибка рушила весь ``_convert()`` (см. worker.py) и вызывала бесконечный
ретрай конвертации одного и того же файла.
"""

import pytest

from utils.proclog import ProcLog


class _FakeVk:
    def __init__(self):
        self.hashes: dict[str, dict] = {}
        self.published: list[tuple[str, str]] = []
        self.expired: list[tuple[str, int]] = []

    async def hset(self, key, mapping):
        for v in mapping.values():
            if not isinstance(v, (bytes, str, int, float)):
                raise TypeError(f"Invalid input of type: {type(v).__name__!r}")
        self.hashes.setdefault(key, {}).update(mapping)

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))

    async def publish(self, channel, payload):
        self.published.append((channel, payload))

    async def hgetall(self, key):
        return self.hashes.get(key, {})


@pytest.mark.asyncio
async def test_set_progress_coerces_bool_done_to_int():
    vk = _FakeVk()
    log = ProcLog(vk)
    await log.set_progress("job1", percent=42.5, eta_sec=10.0, done=False)
    stored = await log.get_progress("job1")
    assert stored["done"] == 0
    assert stored["percent"] == 42.5


@pytest.mark.asyncio
async def test_set_progress_final_done_true_coerced():
    vk = _FakeVk()
    log = ProcLog(vk)
    await log.set_progress("job1", percent=100.0, eta_sec=0.0, done=True)
    stored = await log.get_progress("job1")
    assert stored["done"] == 1


@pytest.mark.asyncio
async def test_set_progress_none_fields_become_empty_string():
    vk = _FakeVk()
    log = ProcLog(vk)
    await log.set_progress("job1", percent=None, eta_sec=None, done=False)
    stored = await log.get_progress("job1")
    assert stored["percent"] == ""
    assert stored["eta_sec"] == ""


@pytest.mark.asyncio
async def test_set_progress_publishes_json_event():
    vk = _FakeVk()
    log = ProcLog(vk)
    await log.set_progress("job1", percent=50.0, done=False)
    assert len(vk.published) == 1
    channel, payload = vk.published[0]
    assert channel == "proclog:progress-events:job1"
    assert '"percent": 50.0' in payload
