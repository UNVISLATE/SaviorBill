"""Юнит-тесты общего фонового поллера снапшота инстансов (AUDIT.md §3.5):
один поллер на процесс вместо запроса в Valkey на каждого WS-клиента.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import services.stats_broadcaster as sb_mod
from services.stats_broadcaster import StatsBroadcaster

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_start_populates_snapshot_immediately(monkeypatch):
    calls = {"n": 0}

    async def fake_list_instances(vk):
        calls["n"] += 1
        return {"instances": [{"id": "a"}], "aggregate": {"total": 1}}

    monkeypatch.setattr(sb_mod, "list_instances", fake_list_instances)
    cfg = SimpleNamespace(SYSTEM_STATS_WS_MIN_SEC=60)
    b = StatsBroadcaster(SimpleNamespace(), cfg)
    await b.start()
    try:
        assert calls["n"] == 1
        assert b.snapshot == {"instances": [{"id": "a"}], "aggregate": {"total": 1}}
    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_poll_updates_snapshot_on_fixed_interval_not_per_client(monkeypatch):
    """Число вызовов list_instances не должно расти с числом "клиентов" — оно
    определяется только периодом поллера, не количеством читателей кэша."""
    calls = {"n": 0}

    async def fake_list_instances(vk):
        calls["n"] += 1
        return {"instances": [], "aggregate": {"n": calls["n"]}}

    monkeypatch.setattr(sb_mod, "list_instances", fake_list_instances)
    cfg = SimpleNamespace(SYSTEM_STATS_WS_MIN_SEC=1)
    b = StatsBroadcaster(SimpleNamespace(), cfg)
    # Ускоряем цикл поллинга для теста напрямую, не трогая cfg.
    b._interval = 0.02
    await b.start()
    try:
        # Много "клиентов" просто читают b.snapshot — не вызывая list_instances.
        for _ in range(50):
            _ = b.snapshot
        await asyncio.sleep(0.07)
        # За ~0.07с с периодом 0.02с ожидаем несколько тиков, но не десятки/сотни.
        assert 1 <= calls["n"] <= 6
    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_stop_cancels_background_task(monkeypatch):
    async def fake_list_instances(vk):
        return {"instances": [], "aggregate": {}}

    monkeypatch.setattr(sb_mod, "list_instances", fake_list_instances)
    cfg = SimpleNamespace(SYSTEM_STATS_WS_MIN_SEC=0.01)
    b = StatsBroadcaster(SimpleNamespace(), cfg)
    await b.start()
    task = b._task
    await b.stop()
    assert task.cancelled() or task.done()
    assert b._task is None


@pytest.mark.asyncio
async def test_start_survives_initial_fetch_error(monkeypatch):
    async def failing_list_instances(vk):
        raise RuntimeError("valkey down")

    monkeypatch.setattr(sb_mod, "list_instances", failing_list_instances)
    cfg = SimpleNamespace(SYSTEM_STATS_WS_MIN_SEC=60)
    b = StatsBroadcaster(SimpleNamespace(), cfg)
    await b.start()
    try:
        assert b.snapshot == {"instances": [], "aggregate": {}}
    finally:
        await b.stop()
