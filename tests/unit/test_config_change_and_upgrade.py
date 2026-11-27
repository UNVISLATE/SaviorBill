"""Unit-тесты Этапа 4: отложенная смена конфига (pending_order_config) и мгновенный апгрейд (proration)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from enums import Delivery, PriceType, ServiceAction, UsvcStatus
from models.user_services import UserServicesMngr
from services.billing_executor import BillingExecutor
from services.lifecycle_pricing import resolve_upgrade_quote
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


def _tiered_service(**kw):
    base = dict(
        id=1,
        price=Decimal("100.00"),
        duration=86400 * 30,
        price_type=PriceType.TIERED,
        pricing_config={
            "tiers": [
                {"code": "basic", "title": "Basic", "price": "100.00", "duration": 86400 * 30},
                {"code": "pro", "title": "Pro", "price": "200.00", "duration": 86400 * 30},
            ]
        },
        delivery=Delivery.LUA,
        is_active=True,
        settings={
            "allow_early_renew": True,
            "allow_renew_config_change": True,
            "allow_instant_upgrade": True,
        },
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_apply_renew_schedules_pending_config_change(monkeypatch):
    sched_cfg = []
    sched_exp = []
    monkeypatch.setattr(
        "models.user_services.schedule_apply_config",
        AsyncMock(side_effect=lambda s, uid, dt: sched_cfg.append((uid, dt))),
    )
    monkeypatch.setattr(
        "models.user_services.schedule_service_expire",
        AsyncMock(side_effect=lambda s, uid, dt: sched_exp.append((uid, dt))),
    )

    class _FakeSession:
        async def flush(self):
            pass

    old_exp = datetime.now(timezone.utc) + timedelta(days=10)
    usvc = SimpleNamespace(
        id=12,
        account_id=5,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        price=Decimal("100.00"),
        duration=86400 * 30,
        order_config={"tier": {"code": "basic"}},
        pending_order_config=None,
        pending_apply_at=None,
        expires_at=old_exp,
        private_data={},
    )
    svc = _tiered_service(delivery=Delivery.KEY)
    acc = SimpleNamespace(id=5)

    mngr = UserServicesMngr(_FakeSession(), AsyncMock())
    target_cfg = {"tier": {"code": "pro"}, "settings": {}}
    await mngr.apply_renew(usvc, svc, acc, duration=86400 * 30, target_config=target_cfg)

    # Текущий конфиг не тронут, новый отложен на old_exp
    assert usvc.order_config == {"tier": {"code": "basic"}}
    assert usvc.pending_order_config == target_cfg
    assert usvc.pending_apply_at == old_exp
    assert usvc.expires_at == old_exp + timedelta(days=30)
    assert sched_cfg == [(12, old_exp)]
    assert sched_exp == [(12, usvc.expires_at)]


@pytest.mark.asyncio
async def test_exec_svc_apply_config_runs_reconfigure_and_swaps(monkeypatch):
    monkeypatch.setattr(
        "services.billing_executor.lock_account",
        AsyncMock(return_value=SimpleNamespace(id=5, login="u5")),
    )
    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())

    usvc = SimpleNamespace(
        id=12,
        account_id=5,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        order_config={"tier": {"code": "basic"}},
        pending_order_config={"tier": {"code": "pro"}},
        pending_apply_at=utc_now(),
    )
    svc = _tiered_service()

    class _FakeSession:
        async def get(self, model, pk, **kw):
            name = getattr(model, "__name__", "")
            if name == "UserServicesModel":
                return usvc
            if name == "ServiceModel":
                return svc
            return None

    actions_called = []

    class _FakeMngr:
        dispatcher = None

        async def run_action(self, u, s, a, action):
            actions_called.append((action, u._reconfigure_ctx))

    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    monkeypatch.setattr(executor, "_usvc_mngr", AsyncMock(return_value=_FakeMngr()))

    await executor.exec_svc_apply_config(_FakeSession(), 12)

    assert len(actions_called) == 1
    assert actions_called[0][0] == ServiceAction.RECONFIGURE
    assert actions_called[0][1]["old_config"] == {"tier": {"code": "basic"}}
    assert actions_called[0][1]["new_config"] == {"tier": {"code": "pro"}}
    assert usvc.order_config == {"tier": {"code": "pro"}}
    assert usvc.pending_order_config is None
    assert usvc.pending_apply_at is None


def test_resolve_upgrade_quote_proration_and_downgrade_block():
    now = utc_now()
    svc = _tiered_service()
    # Осталось ровно половина периода (15 из 30 дней) -> доплата (200 - 100) * 0.5 = 50.00
    usvc = SimpleNamespace(
        id=20,
        status=UsvcStatus.ACTIVE,
        price=Decimal("100.00"),
        duration=86400 * 30,
        expires_at=now + timedelta(days=15),
        order_config={"tier": {"code": "basic"}},
    )
    q = resolve_upgrade_quote(usvc, svc, tier_code="pro", now=now)
    assert q.delta_price == Decimal("50.00")
    assert q.new_price == Decimal("200.00")

    # Мгновенный даунгрейд запрещён (400)
    usvc_pro = SimpleNamespace(
        id=21,
        status=UsvcStatus.ACTIVE,
        price=Decimal("200.00"),
        duration=86400 * 30,
        expires_at=now + timedelta(days=15),
        order_config={"tier": {"code": "pro"}},
    )
    with pytest.raises(HTTPException) as exc:
        resolve_upgrade_quote(usvc_pro, svc, tier_code="basic", now=now)
    assert exc.value.status_code == 400
