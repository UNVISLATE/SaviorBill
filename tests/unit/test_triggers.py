"""Юнит-тесты диспетчера триггеров (логика без БД/SMTP/Lua)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrations.triggers import TriggerDispatcher, TriggerEvent
from integrations.triggers.base import BaseAction, dig

pytestmark = pytest.mark.unit


def test_dig_nested():
    ctx = {"user": {"email": "a@b.c"}, "n": 1}
    assert dig(ctx, "user.email") == "a@b.c"
    assert dig(ctx, "n") == 1
    assert dig(ctx, "user.missing") is None
    assert dig(ctx, "missing.deep") is None


def test_match_empty_cond_true():
    assert TriggerDispatcher._match({}, {"a": 1}) is True


def test_match_all_pairs():
    ctx = {"payment": {"target": "service"}, "x": 5}
    assert TriggerDispatcher._match({"payment.target": "service"}, ctx) is True
    assert TriggerDispatcher._match({"payment.target": "balance"}, ctx) is False
    assert TriggerDispatcher._match({"x": 5, "payment.target": "service"}, ctx) is True


class _FakeTrigMngr:
    def __init__(self, rows):
        self._rows = rows

    async def by_event(self, event):
        return [r for r in self._rows if r.event == event and r.is_active]


class _RecAction(BaseAction):
    """Действие-заглушка: записывает вызовы и возвращает заданный результат."""

    key = "rec"

    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    async def run(self, event, ctx, config):
        self.calls.append((event, ctx, config))
        return self.ok


def _trig(**kw):
    kw.setdefault("is_active", True)
    kw.setdefault("cond", {})
    kw.setdefault("config", {})
    kw.setdefault("action", "rec")
    return SimpleNamespace(**kw)


@pytest.mark.asyncio
async def test_fire_runs_matching():
    action = _RecAction()
    trigs = [_trig(id=1, event=TriggerEvent.USER_REGISTERED)]
    disp = TriggerDispatcher(_FakeTrigMngr(trigs), {"rec": action})

    n = await disp.fire(TriggerEvent.USER_REGISTERED, {"user": {"email": "x@y.z"}})
    assert n == 1
    assert action.calls[0][1]["user"]["email"] == "x@y.z"


@pytest.mark.asyncio
async def test_fire_skips_on_unmet_cond():
    action = _RecAction()
    trigs = [
        _trig(id=1, event="payment.paid", cond={"payment.target": "service"}),
    ]
    disp = TriggerDispatcher(_FakeTrigMngr(trigs), {"rec": action})

    ctx = {"user": {"email": "x@y.z"}, "payment": {"target": "balance"}}
    assert await disp.fire("payment.paid", ctx) == 0
    assert action.calls == []


@pytest.mark.asyncio
async def test_fire_skips_unknown_action():
    disp = TriggerDispatcher(_FakeTrigMngr([_trig(id=1, event="e", action="nope")]), {})
    assert await disp.fire("e", {}) == 0


@pytest.mark.asyncio
async def test_fire_best_effort_on_action_error():
    class _Boom(BaseAction):
        key = "rec"

        async def run(self, event, ctx, config):
            raise RuntimeError("boom")

    trigs = [_trig(id=1, event="e"), _trig(id=2, event="e")]
    disp = TriggerDispatcher(_FakeTrigMngr(trigs), {"rec": _Boom()})
    # Ошибки действий не пробрасываются; успешных — ноль.
    assert await disp.fire("e", {}) == 0
