"""Unit-тесты Этапа 5: автопродление с баланса (успех и недостаток средств без отключения)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from enums import Delivery, PriceType, UsvcStatus
from services.billing_executor import BillingExecutor
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_exec_svc_auto_renew_success_and_resets_errors(monkeypatch):
    acc = SimpleNamespace(
        id=7,
        login="u7",
        balance=Decimal("250.00"),
        bonus_balance=Decimal("0.00"),
    )
    monkeypatch.setattr("services.billing_executor.lock_account", AsyncMock(return_value=acc))
    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())

    usvc = SimpleNamespace(
        id=31,
        account_id=7,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        auto_renew=True,
        auto_renew_attempts=1,
        auto_renew_last_error="insufficient_balance",
        price=Decimal("100.00"),
        duration=86400 * 30,
        expires_at=utc_now() + timedelta(hours=12),
        order_config={},
        pending_order_config=None,
    )
    svc = SimpleNamespace(
        id=1,
        price=Decimal("100.00"),
        duration=86400 * 30,
        price_type=PriceType.FIXED,
        pricing_config={},
        delivery=Delivery.KEY,
        is_active=True,
        settings={"allow_early_renew": True, "allow_auto_renew": True},
    )

    class _FakeSession:
        async def get(self, model, pk, **kw):
            name = getattr(model, "__name__", "")
            if name == "UserServicesModel":
                return usvc
            if name == "ServiceModel":
                return svc
            return None

    renewed = []

    class _FakeMngr:
        dispatcher = None

        async def apply_renew(self, u, s, a, *, duration):
            renewed.append((u.id, duration))
            u.expires_at = u.expires_at + timedelta(seconds=duration)

    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    monkeypatch.setattr(executor, "_usvc_mngr", AsyncMock(return_value=_FakeMngr()))

    await executor.exec_svc_auto_renew(_FakeSession(), 31)

    assert acc.balance == Decimal("150.00")
    assert renewed == [(31, 86400 * 30)]
    assert usvc.auto_renew_attempts == 0
    assert usvc.auto_renew_last_error is None


@pytest.mark.asyncio
async def test_exec_svc_auto_renew_insufficient_balance_keeps_active_and_retries(monkeypatch):
    acc = SimpleNamespace(
        id=7,
        login="u7",
        balance=Decimal("10.00"),
        bonus_balance=Decimal("0.00"),
    )
    monkeypatch.setattr("services.billing_executor.lock_account", AsyncMock(return_value=acc))
    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())

    retries = []
    monkeypatch.setattr(
        "services.billing_executor.schedule_auto_renew",
        AsyncMock(side_effect=lambda s, uid, dt: retries.append((uid, dt))),
    )

    exp = datetime.now(timezone.utc) + timedelta(hours=20)
    usvc = SimpleNamespace(
        id=32,
        account_id=7,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        auto_renew=True,
        auto_renew_attempts=0,
        auto_renew_last_error=None,
        price=Decimal("100.00"),
        duration=86400 * 30,
        expires_at=exp,
        order_config={},
        pending_order_config=None,
    )
    svc = SimpleNamespace(
        id=1,
        price=Decimal("100.00"),
        duration=86400 * 30,
        price_type=PriceType.FIXED,
        pricing_config={},
        delivery=Delivery.KEY,
        is_active=True,
        settings={"allow_early_renew": True, "allow_auto_renew": True},
    )

    class _FakeSession:
        async def get(self, model, pk, **kw):
            name = getattr(model, "__name__", "")
            if name == "UserServicesModel":
                return usvc
            if name == "ServiceModel":
                return svc
            return None

    class _FakeMngr:
        dispatcher = None

    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    monkeypatch.setattr(executor, "_usvc_mngr", AsyncMock(return_value=_FakeMngr()))

    await executor.exec_svc_auto_renew(_FakeSession(), 32)

    assert usvc.status == UsvcStatus.ACTIVE
    assert usvc.auto_renew_last_error == "insufficient_balance"
    assert usvc.auto_renew_attempts == 1
    assert len(retries) == 1
    assert retries[0][0] == 32
    assert retries[0][1] == exp - timedelta(hours=1)
