from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from core.config import AppConfig
from enums import PriceType, UsvcStatus
from services.billing_executor import BillingExecutor
from services.pricing import ResolvedOrder, apply_discount_with_floor, assert_promotions_allowed
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


def test_assert_promotions_allowed_blocks_disabled_service() -> None:
    svc = SimpleNamespace(settings={"allow_promotions": False})
    with pytest.raises(HTTPException) as exc:
        assert_promotions_allowed(svc)
    assert exc.value.status_code == 400

    svc_ok = SimpleNamespace(settings={"allow_promotions": True})
    assert_promotions_allowed(svc_ok)


def test_apply_discount_with_floor_enforces_custom_nominal_floor() -> None:
    svc = SimpleNamespace(price_type=PriceType.CUSTOM)
    resolved = ResolvedOrder(
        price=Decimal("80.00"),
        duration=30,
        effective_settings={},
        order_config={"nominal_amount": "50.00", "allow_sub_nominal_discount": False},
    )
    final_price = apply_discount_with_floor(
        svc, resolved, Decimal("40.00"), custom_amount=Decimal("50.00")
    )
    assert final_price == Decimal("50.00")


@pytest.mark.asyncio
async def test_delivery_retry_skips_refund_when_delivery_credit_already_set() -> None:
    usvc = SimpleNamespace(
        id=42,
        account_id=7,
        service_id=3,
        status=UsvcStatus.FAILED,
        error="timeout",
        delivery_attempts=99,
        price=Decimal("100.00"),
        paid_balance=Decimal("100.00"),
        paid_bonus=Decimal("0.00"),
        private_data={
            "delivery_credit": {
                "balance": "100.00",
                "bonus": "0.00",
                "reason": "instant_refund_on_fail",
            }
        },
        delivered_at=None,
        expires_at=None,
    )
    acc = SimpleNamespace(id=7, balance=Decimal("100.00"), bonus_balance=Decimal("0.00"))
    service = SimpleNamespace(id=3, delivery_type="lua", delivery_config={}, duration_days=30)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[usvc, service])
    session.scalar = AsyncMock(return_value=acc)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    vk = MagicMock()
    vk.zadd = AsyncMock()
    vk.zrem = AsyncMock()
    vk.delete = AsyncMock()
    vk.get = AsyncMock(return_value=None)
    vk.incr = AsyncMock(return_value=99)  # exceed max attempts to trigger refund branch
    vk.expire = AsyncMock()

    cfg = AppConfig(SECRET_KEY="x" * 32, DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
    executor = BillingExecutor(vk, cfg)

    # Patch UserServicesMngr.deliver to keep FAILED status
    from unittest.mock import patch

    with (
        patch("services.billing_executor.UserServicesMngr") as mngr_cls,
        patch("services.billing_executor.build_dispatcher") as disp_fn,
        patch("services.billing_executor.lock_account", new=AsyncMock(return_value=acc)),
    ):
        mngr_cls.return_value.deliver = AsyncMock(return_value=usvc)
        disp_fn.return_value.fire = AsyncMock()

        await executor.exec_delivery_retry(session, 42)

    # Balance must NOT be credited a second time
    assert acc.balance == Decimal("100.00")


@pytest.mark.asyncio
async def test_delete_provider_returns_409_when_payments_exist() -> None:
    from api.v1.admin.purchases import delete_provider

    prov = SimpleNamespace(id=1, slug="stripe")
    session = SimpleNamespace(
        get=AsyncMock(return_value=prov),
        scalar=AsyncMock(return_value=55),
        delete=AsyncMock(),
        commit=AsyncMock(),
    )

    with pytest.raises(HTTPException) as exc:
        await delete_provider(1, session=session)
    assert exc.value.status_code == 409
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_my_media_job_respects_admin_perm_and_blocks_foreign_user() -> None:
    from api.v1.user.media import cancel_my_media_job

    jobs = SimpleNamespace(active_for_owner=AsyncMock(return_value=[]))
    vk = SimpleNamespace(
        hget=AsyncMock(return_value=b"99"),
        set=AsyncMock(),
        hset=AsyncMock(),
        publish=AsyncMock(),
    )

    # Foreign regular user -> 404
    regular_acc = SimpleNamespace(id=1, role=SimpleNamespace(key="user", perms={}))
    req_regular = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as exc:
        await cancel_my_media_job(
            req_regular, "tok10", acc=regular_acc, jobs=jobs, vk=vk
        )
    assert exc.value.status_code == 404

    # Admin with admin.media.manage_any -> allowed
    admin_acc = SimpleNamespace(
        id=2,
        role=SimpleNamespace(key="admin", perms={"admin": {"media": {"manage_any": True}}}),
    )
    res = await cancel_my_media_job(
        req_regular, "tok10", acc=admin_acc, jobs=jobs, vk=vk
    )
    assert res["ok"] is True
    vk.set.assert_awaited_once()
    vk.publish.assert_awaited_once()
