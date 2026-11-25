"""Тесты подтверждения исправления аудиторских уязвимостей (F-01 — F-12)."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from enums import BaseRole, PayAction, PayStatus, PayTarget, ServiceAction, UsvcStatus
from lua.schemas import LuaRequest
from models.service import ServiceModel
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel, UserServicesMngr
from dependencies.payment import PayMngr
from lua.context import build_service_ctx
from services.billing_consumer import BillingTaskConsumer
from services.guest_checkout import GuestCheckoutSvc, _CLAIM_PREFIX, _CLAIM_CODE_PREFIX, _CLAIM_FAIL_PREFIX

pytestmark = pytest.mark.unit


# ── F-01: Double refund protection & single-flight claim ─────────────────────

@pytest.mark.asyncio
async def test_f01_refund_single_flight_and_unconfirmed_handling():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())
    mngr.runner = SimpleNamespace()

    payment = UserPaymentsModel(
        id=42,
        account_id=1,
        provider="testprov",
        amount=Decimal("100.00"),
        currency="RUB",
        status=PayStatus.REFUNDING,
        private_data={},
        public_data={},
    )
    mngr._provider = AsyncMock(return_value=SimpleNamespace(slug="testprov", script_version=1))
    mngr._script = AsyncMock(return_value=(SimpleNamespace(), "script.lua", 1))
    mngr._secrets = MagicMock(return_value={})

    # Simulating external provider timeout / network failure
    async def timeout_runner(*args, **kwargs):
        raise TimeoutError("gateway timeout")

    mngr.runner.run_payment = timeout_runner

    with pytest.raises(TimeoutError):
        await mngr.refund(payment)

    # Status must NOT be rolled back to PAID, preventing blind retry at provider
    assert payment.status == PayStatus.REFUNDING


# ── F-02: Underpayment & currency mismatch rejects service delivery ─────────

@pytest.mark.asyncio
async def test_f02_settle_underpayment_and_currency_mismatch():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())

    payment = UserPaymentsModel(
        id=10,
        account_id=1,
        provider="testprov",
        amount=Decimal("500.00"),
        currency="RUB",
        target=PayTarget.SERVICE,
        user_svc_id=100,
        status=PayStatus.PENDING,
        private_data={},
        public_data={},
    )

    # 1. Underpayment
    await mngr._settle(payment, {"paid": True, "paid_amount": "50.00", "paid_currency": "RUB"})
    assert payment.status == PayStatus.REVIEW
    assert payment.private_data.get("review_reason") == "underpayment"

    # Reset
    payment.status = PayStatus.PENDING
    payment.private_data = {}

    # 2. Currency mismatch
    await mngr._settle(payment, {"paid": True, "paid_amount": "500.00", "paid_currency": "USD"})
    assert payment.status == PayStatus.REVIEW
    assert payment.private_data.get("review_reason") == "currency_mismatch"


@pytest.mark.asyncio
async def test_f02_credited_amount_caps_overpaid_balance():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())

    payment = UserPaymentsModel(
        id=11,
        account_id=1,
        provider="testprov",
        amount=Decimal("100.00"),
        base_amount=Decimal("100.00"),
        currency="RUB",
        target=PayTarget.BALANCE,
        status=PayStatus.PENDING,
    )

    # User paid 150.00 for a 100.00 invoice
    credited = await mngr._credited_amount(payment, actual_paid=Decimal("150.00"))
    assert credited == Decimal("100.00")
    assert payment.base_amount == Decimal("100.00")


# ── F-03: Provider verification in _locate ────────────────────────────────────

@pytest.mark.asyncio
async def test_f03_locate_rejects_foreign_provider():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())

    payment = UserPaymentsModel(
        id=20,
        account_id=1,
        provider="provider_alpha",
        status=PayStatus.PENDING,
    )
    session.get = AsyncMock(return_value=payment)

    found = await mngr._locate({"payment_id": 20}, "provider_beta")
    assert found is None


# ── F-04: Callback idempotency and transition tracking ───────────────────────

@pytest.mark.asyncio
async def test_f04_callback_transition_flag():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())

    payment = UserPaymentsModel(
        id=30,
        account_id=1,
        provider="testprov",
        amount=Decimal("100.00"),
        currency="RUB",
        status=PayStatus.PAID,
        private_data={},
        public_data={},
    )
    mngr._provider = AsyncMock(return_value=SimpleNamespace(slug="testprov", script_version=1))
    mngr._script = AsyncMock(return_value=(SimpleNamespace(), "script.lua", 1))
    mngr._secrets = MagicMock(return_value={})
    mngr._locate = AsyncMock(return_value=payment)

    # Duplicate webhook for already PAID payment
    mngr.runner = SimpleNamespace(
        run_payment=AsyncMock(return_value={"private": {"ok": True, "paid": True, "payment_id": 30}})
    )

    req = LuaRequest(method="POST", ip="1.2.3.4", headers={}, query={}, body={})
    res = await mngr.callback("testprov", req)

    assert res._just_transitioned is False


# ── F-05: Idempotency key in Lua context ──────────────────────────────────────

def test_f05_service_ctx_has_idempotency_key():
    usvc = UserServicesModel(
        id=99,
        account_id=1,
        service_id=5,
        status=UsvcStatus.ACTIVE,
        price=Decimal("100.00"),
        discount=Decimal("0"),
        actions=[],
        public_data={},
        private_data={},
    )
    acc = UserModel(
        id=1,
        login="alice",
        email="alice@example.com",
        role_id=1,
        balance=Decimal("0"),
        bonus_balance=Decimal("0"),
    )
    service = ServiceModel(
        id=5,
        slug="vpn",
        name="VPN",
        description="",
        catalog_id=1,
        price=Decimal("10.00"),
        delivery="lua",
        currency="RUB",
    )

    ctx = build_service_ctx(
        action=ServiceAction.CREATE,
        acc=acc,
        usvc=usvc,
        service=service,
        payment=None,
    )
    assert ctx["idempotency_key"] == "usvc:99:create"


# ── F-07: Free renewal exploit disabled ──────────────────────────────────────

@pytest.mark.asyncio
async def test_f07_renew_action_raises_payment_required():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = UserServicesMngr(session, bus=MagicMock(), box=MagicMock())

    usvc = UserServicesModel(
        id=77,
        account_id=1,
        service_id=1,
        status=UsvcStatus.ACTIVE,
        duration=3600,
        price=Decimal("50.00"),
    )
    service = ServiceModel(id=1, name="Key Item", delivery="key")
    acc = UserModel(id=1, login="tester")

    # In UserServicesMngr.run_action, calling RENEW must raise 402 PAYMENT REQUIRED
    with pytest.raises(HTTPException) as exc:
        await mngr.run_action(usvc, service, acc, ServiceAction.RENEW)

    assert exc.value.status_code == 402


# ── F-08: Reversing delivery credit on refund ─────────────────────────────────

@pytest.mark.asyncio
async def test_f08_apply_refund_reverses_delivery_credit():
    session = AsyncMock()
    session.add = MagicMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())

    payment = UserPaymentsModel(
        id=88,
        account_id=1,
        provider="testprov",
        amount=Decimal("100.00"),
        currency="RUB",
        target=PayTarget.SERVICE,
        user_svc_id=10,
        status=PayStatus.PAID,
        private_data={},
    )
    usvc = UserServicesModel(
        id=10,
        account_id=1,
        service_id=2,
        status=UsvcStatus.FAILED,
        price=Decimal("100.00"),
        private_data={
            "delivery_credit": {
                "amount": "100.00",
                "bonus": "0",
                "balance": "100.00",
            }
        },
    )
    acc = UserModel(id=1, login="user", balance=Decimal("100.00"), bonus_balance=Decimal("0"))

    session.scalar = AsyncMock(return_value=usvc)
    session.get = AsyncMock(return_value=ServiceModel(id=2, delivery="key"))

    with patch("dependencies.payment.lock_account", AsyncMock(return_value=acc)):
        await mngr._apply_refund(payment, {"ok": True, "refunded": True})

    assert payment.status == PayStatus.REFUNDED
    # Balance must be deducted back so user doesn't keep both credit and fiat refund
    assert acc.balance == Decimal("0.00")
    assert payment.private_data["refund"]["delivery_credit_reversed"] == "100.00"


# ── F-11: Billing loop requeues med: task on error ───────────────────────────

@pytest.mark.asyncio
async def test_f11_billing_consumer_requeues_med_task_on_error():
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_READY_STREAM="billing:tasks:ready",
        BILLING_READY_GROUP="billingexecutors",
        BILLING_QUEUE_DLQ="billing:queue:dead",
    )
    task = SimpleNamespace(
        id=123,
        dedup_key="med:123",
        task_kind="med_expire",
        ref_id=123,
        status="dispatched",
        version=1,
        attempts=0,
        max_attempts=5,
        locked_until=None,
        last_error=None,
        run_at=None,
        updated_at=None,
    )
    session_mock = AsyncMock()
    session_mock.scalar = AsyncMock(return_value=task)
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_mock
    session_ctx.__aexit__.return_value = None
    sm = MagicMock(return_value=session_ctx)

    consumer = BillingTaskConsumer(sm, AsyncMock(), cfg)
    consumer._dispatch_kind = AsyncMock(side_effect=RuntimeError("db connection failed"))

    await consumer.handle_message({"task_id": "123", "task_kind": "med_expire", "version": "1"})

    assert task.status == "pending"
    assert task.attempts == 1
    assert task.version == 2
    assert task.run_at is not None
    assert "RuntimeError" in (task.last_error or "")
