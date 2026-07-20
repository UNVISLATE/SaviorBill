"""Юнит-тест: Worker._process_one не запускает дублирующую обработку одного и
того же token+op, если лок уже удержан (self-reclaim долгой конвертации или
другая реплика воркера) — см. worker.py::_process_one docstring."""

from __future__ import annotations

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
    def __init__(self, *, pre_locked: set[str] | None = None) -> None:
        self.acked: list[str] = []
        self._locks: set[str] = set(pre_locked or ())
        self.deleted: list[str] = []

    async def xack(self, *_a, **_kw) -> None:
        self.acked.append(_a[-1])

    async def set(self, key, _value, *, nx=False, ex=None):  # noqa: ANN001
        if nx and key in self._locks:
            return None
        self._locks.add(key)
        return True

    async def delete(self, key) -> None:  # noqa: ANN001
        self.deleted.append(key)
        self._locks.discard(key)


def _make_worker(vk: _FakeVk) -> Worker:
    return Worker(cfg=_FakeCfg(), vk=vk, storage=None, settings=None, task_log=None, proc_log=None)


async def test_duplicate_in_flight_task_is_skipped_not_handled(monkeypatch):
    # Симулируем: op:token уже в обработке (лок удержан) — например,
    # self-reclaim подхватил PEL-запись долгой конвертации, которая ещё жива.
    vk = _FakeVk(pre_locked={"media:joblock:convert:tok1"})
    worker = _make_worker(vk)
    handled: list[dict] = []

    async def fake_handle(data: dict) -> None:
        handled.append(data)

    monkeypatch.setattr(worker, "_handle", fake_handle)

    signed = sign_fields("shared-secret", {"op": "convert", "token": "tok1"})
    await worker._process_one("1-1", signed)

    assert handled == []  # дубликат не обработан
    assert vk.acked == ["1-1"]  # но эта доставка подтверждена
    assert vk.deleted == []  # чужой лок не тронут


async def test_free_lock_is_acquired_and_released_after_handling(monkeypatch):
    vk = _FakeVk()
    worker = _make_worker(vk)
    handled: list[dict] = []

    async def fake_handle(data: dict) -> None:
        # В момент обработки лок должен быть удержан.
        assert "media:joblock:convert:tok1" in vk._locks
        handled.append(data)

    monkeypatch.setattr(worker, "_handle", fake_handle)

    signed = sign_fields("shared-secret", {"op": "convert", "token": "tok1"})
    await worker._process_one("1-1", signed)

    assert len(handled) == 1
    assert vk.acked == ["1-1"]
    assert vk.deleted == ["media:joblock:convert:tok1"]  # лок освобождён после обработки
    assert "media:joblock:convert:tok1" not in vk._locks
