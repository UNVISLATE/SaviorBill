"""Юнит-тест: MediaResults отклоняет media:results с неверной/отсутствующей
подписью, не вызывая запись в БД."""

from __future__ import annotations

import asyncio

import pytest

from services.media_results import MediaResults
from security.sec.bus_sign import sign_fields

pytestmark = pytest.mark.unit


class _FakeCfg:
    MEDIA_RESULT_STREAM = "media:results"
    MEDIA_RESULT_GROUP = "billing"
    MEDIA_RESULT_MAX_ATTEMPTS = 3
    BUS_SIGNING_KEY = "shared-secret"
    instance_id = "test-instance"


class _FakeVk:
    """Отдаёт одну запись из xreadgroup один раз, затем блокируется навечно."""

    def __init__(self, entries: list[tuple[str, dict]]) -> None:
        self._entries = entries
        self._served = False
        self.acked: list[str] = []

    async def xgroup_create(self, *_a, **_kw) -> None:
        return None

    async def xreadgroup(self, *_a, **_kw):
        if not self._served:
            self._served = True
            return [("media:results", self._entries)]
        await asyncio.sleep(3600)  # блокируемся, пока тест не отменит задачу

    async def xack(self, *_a, **_kw) -> None:
        self.acked.append(_a[-1])


@pytest.mark.asyncio
async def test_unsigned_result_rejected_not_handled(monkeypatch):
    vk = _FakeVk([("1-1", {"op": "convert", "token": "tok1"})])  # без ts/sig
    mr = MediaResults(sessionmaker=None, vk=vk, cfg=_FakeCfg())

    handled: list[dict] = []

    async def fake_handle(_msg_id: str, data: dict) -> None:
        handled.append(data)

    monkeypatch.setattr(mr, "_handle", fake_handle)

    task = asyncio.create_task(mr._run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert handled == []  # подделка не должна попасть в обработчик записи в БД
    assert vk.acked == ["1-1"]  # но ack всё равно происходит (не через reclaim)


@pytest.mark.asyncio
async def test_correctly_signed_result_is_handled(monkeypatch):
    signed = sign_fields("shared-secret", {"op": "convert", "token": "tok1"})
    vk = _FakeVk([("1-1", signed)])
    mr = MediaResults(sessionmaker=None, vk=vk, cfg=_FakeCfg())

    handled: list[dict] = []

    async def fake_handle(_msg_id: str, data: dict) -> None:
        handled.append(data)

    monkeypatch.setattr(mr, "_handle", fake_handle)

    task = asyncio.create_task(mr._run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(handled) == 1
    assert handled[0]["token"] == "tok1"


@pytest.mark.asyncio
async def test_failure_does_not_ack_until_exhausted(monkeypatch):
    signed = sign_fields("shared-secret", {"op": "convert", "token": "tok1"})
    vk = _FakeVk([("1-1", signed)])
    vk.dlq = []

    async def fake_xadd(stream, data):
        vk.dlq.append((stream, data))

    vk.xadd = fake_xadd

    mr = MediaResults(sessionmaker=None, vk=vk, cfg=_FakeCfg())

    # 1. Первый сбой: попытка 1 из 3 -> НЕ должен делать xack
    async def fake_fail_once(_msg_id: str, data: dict):
        return False  # not exhausted

    monkeypatch.setattr(mr, "_handle", lambda *_: (_ for _ in ()).throw(RuntimeError("DB error")))
    monkeypatch.setattr(mr, "_on_failure", fake_fail_once)

    task = asyncio.create_task(mr._run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert vk.acked == []  # не должно ack-ить при первой ошибке!

    # 2. Исчерпание попыток: _on_failure возвращает True -> xack вызывается
    vk2 = _FakeVk([("1-2", signed)])
    mr2 = MediaResults(sessionmaker=None, vk=vk2, cfg=_FakeCfg())

    async def fake_fail_exhausted(_msg_id: str, data: dict):
        return True  # exhausted, sent to DLQ

    monkeypatch.setattr(mr2, "_handle", lambda *_: (_ for _ in ()).throw(RuntimeError("DB fatal error")))
    monkeypatch.setattr(mr2, "_on_failure", fake_fail_exhausted)

    task2 = asyncio.create_task(mr2._run())
    await asyncio.sleep(0.05)
    task2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task2

    assert vk2.acked == ["1-2"]  # подтверждается только после ухода в DLQ
