"""Мёртвые очереди: просмотр и повтор задач (AUDIT.md §2.3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.dlq import DLQ_QUEUES, DeadLetters

pytestmark = pytest.mark.unit


class _FakeValkey:
    """Мини-Valkey со стримами (списки кортежей) и одним zset."""

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.deleted_keys: list[str] = []

    async def xlen(self, key: str) -> int:
        return len(self.streams.get(key, []))

    async def xrevrange(self, key: str, count: int = 10):
        return list(reversed(self.streams.get(key, [])))[:count]

    async def xrange(self, key: str, min: str, max: str, count: int = 1):
        return [e for e in self.streams.get(key, []) if e[0] == min][:count]

    async def xadd(self, key: str, fields: dict, **_kw) -> str:
        entries = self.streams.setdefault(key, [])
        eid = f"{len(entries) + 1}-0"
        entries.append((eid, dict(fields)))
        return eid

    async def xdel(self, key: str, eid: str) -> int:
        entries = self.streams.get(key, [])
        before = len(entries)
        self.streams[key] = [e for e in entries if e[0] != eid]
        return before - len(self.streams[key])

    async def zadd(self, key: str, mapping: dict, **_kw) -> int:
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def delete(self, key: str) -> None:
        self.deleted_keys.append(key)


def _cfg():
    return SimpleNamespace(
        BILLING_QUEUE_DLQ="billing:queue:dead",
        BILLING_QUEUE_KEY="billing:queue",
        MEDIA_TASK_DLQ="media:tasks:dead",
        MEDIA_TASK_STREAM="media:tasks",
        MEDIA_RESULT_DLQ="media:results:dead",
        MEDIA_RESULT_STREAM="media:results",
        MEDIA_TASK_STREAM_MAXLEN=10_000,
        BUS_SIGNING_KEY="k" * 32,
    )


@pytest.mark.asyncio
async def test_overview_reports_every_queue():
    vk = _FakeValkey()
    await vk.xadd("billing:queue:dead", {"member": "svc:5", "ref_id": "5"})
    data = await DeadLetters(vk, _cfg()).overview()
    assert set(data) == set(DLQ_QUEUES)
    assert data["billing"]["total"] == 1
    assert data["billing"]["items"][0]["fields"]["member"] == "svc:5"
    assert data["media_tasks"]["total"] == 0


@pytest.mark.asyncio
async def test_retry_billing_member_returns_to_queue_and_clears_attempts():
    vk = _FakeValkey()
    eid = await vk.xadd(
        "billing:queue:dead", {"member": "svc:5", "ref_id": "5", "attempts": "5"}
    )
    dlq = DeadLetters(vk, _cfg())

    assert await dlq.retry("billing", eid) is True
    assert "svc:5" in vk.zsets["billing:queue"]
    # Без сброса счётчика задача сразу ушла бы обратно в DLQ.
    assert "attempts:svc:action:5" in vk.deleted_keys
    assert await vk.xlen("billing:queue:dead") == 0


@pytest.mark.asyncio
async def test_retry_media_task_resigns_message():
    vk = _FakeValkey()
    eid = await vk.xadd(
        "media:tasks:dead",
        {
            "op": "convert",
            "token": "abc",
            "ts": "1",
            "sig": "stale",
            "attempts": "5",
            "reason": "max attempts exceeded",
        },
    )
    dlq = DeadLetters(vk, _cfg())

    assert await dlq.retry("media_tasks", eid) is True
    _, fields = vk.streams["media:tasks"][0]
    assert fields["token"] == "abc"
    assert fields["sig"] != "stale"  # подпись пересобрана
    assert int(fields["ts"]) > 1  # и метка времени тоже
    assert "attempts" not in fields and "reason" not in fields


@pytest.mark.asyncio
async def test_retry_unknown_entry_returns_false():
    dlq = DeadLetters(_FakeValkey(), _cfg())
    assert await dlq.retry("billing", "404-0") is False


@pytest.mark.asyncio
async def test_drop_removes_without_requeue():
    vk = _FakeValkey()
    eid = await vk.xadd("billing:queue:dead", {"member": "svc:9"})
    dlq = DeadLetters(vk, _cfg())
    assert await dlq.drop("billing", eid) is True
    assert await vk.xlen("billing:queue:dead") == 0
    assert vk.zsets == {}
