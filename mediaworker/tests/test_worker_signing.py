"""Юнит-тест: Worker отклоняет media:tasks с неверной/отсутствующей подписью,
не вызывая обработчик задачи."""

from __future__ import annotations

import asyncio

import pytest

from utils.bus_sign import sign_fields
from utils.worker import Worker

pytestmark = pytest.mark.asyncio


class _FakeCfg:
    task_concurrency = 2
    task_concurrency_image = 2
    task_concurrency_video = 2
    task_stream = "media:tasks"
    group = "mediaworkers"
    consumer = "media-1"
    BUS_SIGNING_KEY = "shared-secret"
    job_lock_ttl_sec = 900


class _FakeVk:
    def __init__(self) -> None:
        self.acked: list[str] = []
        self._locks: set[str] = set()

    async def xack(self, *_a, **_kw) -> None:
        self.acked.append(_a[-1])

    async def set(self, key, _value, *, nx=False, ex=None):  # noqa: ANN001
        if nx and key in self._locks:
            return None
        self._locks.add(key)
        return True

    async def delete(self, key) -> None:  # noqa: ANN001
        self._locks.discard(key)


def _make_worker() -> tuple[Worker, _FakeVk]:
    vk = _FakeVk()
    worker = Worker(
        cfg=_FakeCfg(), vk=vk, storage=None, settings=None, task_log=None, proc_log=None
    )
    return worker, vk


async def test_unsigned_task_rejected_not_handled(monkeypatch):
    worker, vk = _make_worker()
    handled: list[dict] = []

    async def fake_handle(data: dict) -> None:
        handled.append(data)

    monkeypatch.setattr(worker, "_handle", fake_handle)

    await worker._process_one("1-1", {"op": "convert", "token": "tok1"})  # без ts/sig

    assert handled == []
    assert vk.acked == ["1-1"]


async def test_correctly_signed_task_is_handled(monkeypatch):
    worker, vk = _make_worker()
    handled: list[dict] = []

    async def fake_handle(data: dict) -> None:
        handled.append(data)

    monkeypatch.setattr(worker, "_handle", fake_handle)

    signed = sign_fields("shared-secret", {"op": "convert", "token": "tok1"})
    await worker._process_one("1-1", signed)

    assert len(handled) == 1
    assert vk.acked == ["1-1"]
