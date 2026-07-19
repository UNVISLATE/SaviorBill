"""Юнит-тест: Worker.reclaim_once подхватывает зависшие PEL-записи или
отправляет их в DLQ по исчерпанию попыток (AUDIT.md §3.1)."""

from __future__ import annotations

import pytest

from utils.worker import Worker

pytestmark = pytest.mark.asyncio


class _FakeCfg:
    task_concurrency = 2
    task_stream = "media:tasks"
    group = "mediaworkers"
    consumer = "media-1"
    task_dlq_stream = "media:tasks:dead"
    task_stream_maxlen = 1000
    task_max_attempts = 3
    reclaim_min_idle_ms = 60_000
    status_ttl = 3600
    BUS_SIGNING_KEY = ""


class _FakeVk:
    def __init__(self, pending: list[dict], rows: dict[str, dict]) -> None:
        self._pending = pending
        self._rows = rows
        self.acked: list[str] = []
        self.claimed: list[str] = []
        self.dlq: list[dict] = []
        self.status: dict[str, dict] = {}

    async def xpending_range(self, *_a, **_kw):
        return self._pending

    async def xrange(self, _stream, msg_id, _end):
        row = self._rows.get(msg_id)
        return [(msg_id, row)] if row else []

    async def xack(self, *_a, **_kw) -> None:
        self.acked.append(_a[-1])

    async def xclaim(self, _stream, _group, _consumer, *, min_idle_time, message_ids):
        out = []
        for mid in message_ids:
            self.claimed.append(mid)
            row = self._rows.get(mid)
            if row:
                out.append((mid, row))
        return out

    async def xadd(self, stream, fields, **_kw):
        if stream == "media:tasks:dead":
            self.dlq.append(fields)
        return "0-0"

    async def hset(self, key, mapping):
        self.status.setdefault(key, {}).update(mapping)

    async def expire(self, *_a, **_kw) -> None:
        pass


class _FakeTaskLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kw) -> None:
        self.records.append(kw)


def _make_worker(pending, rows):
    vk = _FakeVk(pending, rows)
    task_log = _FakeTaskLog()
    worker = Worker(
        cfg=_FakeCfg(), vk=vk, storage=None, settings=None, task_log=task_log, proc_log=None
    )
    return worker, vk, task_log


async def test_reclaim_below_max_attempts_reprocesses_via_claim(monkeypatch):
    rows = {"1-1": {"op": "convert", "token": "tok1"}}
    pending = [{"message_id": "1-1", "times_delivered": 2}]
    worker, vk, _ = _make_worker(pending, rows)

    processed: list[str] = []

    async def fake_process_one(msg_id, data):
        processed.append(msg_id)

    monkeypatch.setattr(worker, "_process_one", fake_process_one)

    await worker.reclaim_once()

    assert vk.claimed == ["1-1"]
    assert processed == ["1-1"]
    assert vk.dlq == []


async def test_reclaim_above_max_attempts_goes_to_dlq_without_reprocessing(monkeypatch):
    rows = {"1-1": {"op": "convert", "token": "tok1"}}
    pending = [{"message_id": "1-1", "times_delivered": 4}]  # > task_max_attempts(3)
    worker, vk, task_log = _make_worker(pending, rows)

    processed: list[str] = []
    monkeypatch.setattr(worker, "_process_one", lambda *a, **kw: processed.append(a))

    await worker.reclaim_once()

    assert processed == []
    assert vk.claimed == []
    assert vk.acked == ["1-1"]
    assert len(vk.dlq) == 1
    assert vk.dlq[0]["token"] == "tok1"
    assert task_log.records[-1]["state"] == "failed"


async def test_reclaim_no_pending_is_noop():
    worker, vk, _ = _make_worker([], {})
    await worker.reclaim_once()
    assert vk.acked == []
    assert vk.claimed == []
