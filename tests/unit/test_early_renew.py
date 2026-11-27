"""Unit-тесты Этапа 3: преждевременное продление существующей услуги (баланс + PayTarget.RENEW)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from enums import Delivery, PayTarget, PriceType, UsvcStatus
from models.user_services import UserServicesMngr
from schemas.payments import PaymentCreate
from services.lifecycle_pricing import assert_renew_allowed, resolve_renew_quote
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


def _make_service(**kw):
    base = dict(
        id=1,
        price=Decimal("100.00"),
        duration=2592000,
        price_type=PriceType.FIXED,
        pricing_config={},
        delivery=Delivery.LUA,
        is_active=True,
        settings={
            "allow_early_renew": True,
            "renew_price_policy": "current",
        },
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _make_usvc(**kw):
    base = dict(
        id=10,
        account_id=5,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        price=Decimal("80.00"),
        duration=2592000,
        order_config={},
        expires_at=utc_now() + timedelta(days=10),
        private_data={},
        public_data={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_assert_renew_allowed_checks_applicability_and_windows():
    svc_off = _make_service(settings={"allow_early_renew": False})
    usvc = _make_usvc()
    with pytest.raises(HTTPException) as exc:
        assert_renew_allowed(usvc, svc_off)
    assert exc.value.status_code == 400

    svc_win = _make_service(
        settings={"allow_early_renew": True, "early_renew_window_sec": 86400}
    )
    with pytest.raises(HTTPException) as exc2:
        assert_renew_allowed(usvc, svc_win)
    assert exc2.value.status_code == 400

    svc_max = _make_service(
        settings={"allow_early_renew": True, "max_expires_ahead_sec": 86400 * 15}
    )
    with pytest.raises(HTTPException) as exc3:
        assert_renew_allowed(usvc, svc_max, duration_sec=86400 * 30)
    assert exc3.value.status_code == 400

    usvc_prov = _make_usvc(status=UsvcStatus.PROVISIONING)
    with pytest.raises(HTTPException) as exc4:
        assert_renew_allowed(usvc_prov, _make_service())
    assert exc4.value.status_code == 409


def test_resolve_renew_quote_locked_vs_current_and_config_change():
    svc = _make_service(
        price=Decimal("120.00"),
        settings={"allow_early_renew": True, "renew_price_policy": "locked"},
    )
    usvc = _make_usvc(price=Decimal("80.00"))
    q = resolve_renew_quote(usvc, svc)
    assert q.price == Decimal("80.00")
    assert q.config_changed is False

    svc_cur = _make_service(
        price=Decimal("120.00"),
        settings={"allow_early_renew": True, "renew_price_policy": "current"},
    )
    q2 = resolve_renew_quote(usvc, svc_cur)
    assert q2.price == Decimal("120.00")


def test_payment_create_schema_supports_renew():
    p = PaymentCreate(provider="yookassa", target=PayTarget.RENEW, user_svc_id=42)
    assert p.target == PayTarget.RENEW
    assert p.user_svc_id == 42

    with pytest.raises(ValueError):
        PaymentCreate(provider="yookassa", target=PayTarget.RENEW)


@pytest.mark.asyncio
async def test_apply_renew_shifts_expires_at_and_schedules_expire(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "models.user_services.schedule_service_expire",
        AsyncMock(side_effect=lambda s, uid, dt: scheduled.append((uid, dt))),
    )

    class _FakeSession:
        async def flush(self):
            pass

    start_exp = datetime.now(timezone.utc) + timedelta(days=5)
    usvc = _make_usvc(expires_at=start_exp)
    svc = _make_service(delivery=Delivery.KEY)
    acc = SimpleNamespace(id=5)

    mngr = UserServicesMngr(_FakeSession(), AsyncMock())
    await mngr.apply_renew(usvc, svc, acc, duration=86400 * 30)

    assert usvc.expires_at == start_exp + timedelta(days=30)
    assert len(scheduled) == 1
    assert scheduled[0] == (10, usvc.expires_at)

    # Истёкшая услуга при продлении продлевается от текущего момента и становится ACTIVE
    usvc_exp = _make_usvc(
        status=UsvcStatus.EXPIRED,
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    before = utc_now()
    await mngr.apply_renew(usvc_exp, svc, acc, duration=86400 * 30)
    assert usvc_exp.status == UsvcStatus.ACTIVE
    assert usvc_exp.expires_at >= before + timedelta(days=29)
