"""Юнит-тест: Worker отклоняет media:tasks с неверной/отсутствующей подписью,
не вызывая обработчик задачи (AUDIT.md H1)."""

from __future__ import annotations

import asyncio

import pytest

from utils.bus_sign import sign_fields
from utils.worker import Worker

pytestmark = pytest.mark.asyncio


class _FakeCfg:
    task_concurrency = 2
    task_stream = "media:tasks"
    group = "mediaworkers"
    BUS_SIGNING_KEY = "shared-secret"


class _FakeVk:
    def __init__(self) -> None:
        self.acked: list[str] = []

    async def xack(self, *_a, **_kw) -> None:
        self.acked.append(_a[-1])


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
