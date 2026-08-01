"""Повтор выдачи и компенсация внутренним балансом (AUDIT.md §3.1, решение D7)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from enums import UsvcStatus
from services.billing_loop import BillingLoop

pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self, objs: dict) -> None:
        self._objs = objs
        self.added: list = []

    async def get(self, model, pk):
        return self._objs.get((model.__name__, pk))

    async def flush(self) -> None:
        pass

    def add(self, obj) -> None:
        self.added.append(obj)


def _usvc(**kw):
    base = dict(
        id=1,
        account_id=7,
        service_id=3,
        status=UsvcStatus.FAILED,
        price=Decimal("100.00"),
        delivery_attempts=0,
        private_data={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _loop() -> BillingLoop:
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    loop = BillingLoop.__new__(BillingLoop)
    loop.cfg = cfg
    loop.vk = AsyncMock()
    return loop


@pytest.mark.asyncio
async def test_compensation_credits_internal_balance_once(monkeypatch):
    loop = _loop()
    usvc = _usvc()
    acc = SimpleNamespace(id=7, balance=Decimal("5.00"))
    session = _FakeSession({})

    monkeypatch.setattr(
        "services.billing_loop.lock_account", AsyncMock(return_value=acc)
    )
    loop._audit_delivery = AsyncMock()

    await loop._compensate_delivery(session, usvc)
    assert acc.balance == Decimal("105.00")
    assert usvc.private_data["delivery_credit"]["amount"] == "100.00"

    # Повторный вызов не начисляет второй раз.
    await loop._compensate_delivery(session, usvc)
    assert acc.balance == Decimal("105.00")


@pytest.mark.asyncio
async def test_compensation_skipped_for_free_service(monkeypatch):
    loop = _loop()
    usvc = _usvc(price=Decimal("0"))
    acc = SimpleNamespace(id=7, balance=Decimal("5.00"))
    monkeypatch.setattr(
        "services.billing_loop.lock_account", AsyncMock(return_value=acc)
    )
    loop._audit_delivery = AsyncMock()

    await loop._compensate_delivery(_FakeSession({}), usvc)
    assert acc.balance == Decimal("5.00")
    assert "delivery_credit" not in usvc.private_data


@pytest.mark.asyncio
async def test_retry_reschedules_until_attempts_exhausted(monkeypatch):
    loop = _loop()
    usvc = _usvc(delivery_attempts=0)
    service = SimpleNamespace(id=3)
    acc = SimpleNamespace(id=7, balance=Decimal("0"))
    session = _FakeSession(
        {("UserServicesModel", 1): usvc, ("ServiceModel", 3): service}
    )

    monkeypatch.setattr(
        "services.billing_loop.lock_account", AsyncMock(return_value=acc)
    )
    loop._delivery_limits = AsyncMock(return_value=(3, 60))
    loop._audit_delivery = AsyncMock()

    async def _deliver(u, _s, _a):
        u.delivery_attempts += 1  # выдача снова упала

    loop._usvc_mngr = AsyncMock(
        return_value=SimpleNamespace(deliver=AsyncMock(side_effect=_deliver))
    )

    await loop._exec_delivery_retry(session, 1)
    assert usvc.delivery_attempts == 1
    loop.vk.zadd.assert_awaited()  # поставлен повтор
    assert "delivery_credit" not in usvc.private_data


@pytest.mark.asyncio
async def test_exhausted_attempts_go_straight_to_compensation(monkeypatch):
    loop = _loop()
    usvc = _usvc(delivery_attempts=3)
    acc = SimpleNamespace(id=7, balance=Decimal("0"))
    session = _FakeSession({("UserServicesModel", 1): usvc})

    monkeypatch.setattr(
        "services.billing_loop.lock_account", AsyncMock(return_value=acc)
    )
    loop._delivery_limits = AsyncMock(return_value=(3, 60))
    loop._audit_delivery = AsyncMock()

    await loop._exec_delivery_retry(session, 1)
    assert acc.balance == Decimal("100.00")


@pytest.mark.asyncio
async def test_active_service_is_not_retried():
    loop = _loop()
    usvc = _usvc(status=UsvcStatus.ACTIVE)
    session = _FakeSession({("UserServicesModel", 1): usvc})
    await loop._exec_delivery_retry(session, 1)
    loop.vk.zadd.assert_not_awaited()
