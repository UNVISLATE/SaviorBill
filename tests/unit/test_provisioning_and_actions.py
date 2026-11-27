"""Unit-тесты Этапа 1: развод stop/freeze, UsvcStatus.PROVISIONING и Lua poll."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from enums import Delivery, ScriptKind, ServiceAction, UsvcStatus
from lua.context import build_service_ctx
from lua.integrations.delivery import LuaService, _clamp_poll_config
from models.user_services import UserServicesMngr
from services.billing_executor import BillingExecutor
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self, objs: dict | None = None) -> None:
        self._objs = objs or {}
        self.added: list = []

    async def get(self, model, pk, **kwargs):
        name = getattr(model, "__name__", str(model))
        return self._objs.get((name, pk))

    async def scalar(self, stmt):
        for k, obj in self._objs.items():
            if k[0] == "UserServicesModel":
                return obj
        return None

    async def flush(self) -> None:
        pass

    def add(self, obj) -> None:
        self.added.append(obj)


def test_idempotency_key_unique_for_repeatable_actions():
    acc = SimpleNamespace(id=1, login="u1", email="u1@example.com", balance=Decimal("100"))
    service = SimpleNamespace(
        id=2, name="VPS", slug="vps", currency="RUB", settings={}, params={}, price=Decimal("100")
    )
    usvc = SimpleNamespace(
        id=10,
        price=Decimal("100"),
        order_config={},
        public_data={},
        private_data={},
        custom_public={},
        custom_private={},
        expires_at=None,
        status=UsvcStatus.ACTIVE,
    )
    ctx_create_1 = build_service_ctx(ServiceAction.CREATE, acc, usvc, service)
    ctx_create_2 = build_service_ctx(ServiceAction.CREATE, acc, usvc, service)
    assert ctx_create_1["idempotency_key"] == "usvc:10:create"
    assert ctx_create_2["idempotency_key"] == "usvc:10:create"

    ctx_poll_1 = build_service_ctx(ServiceAction.POLL, acc, usvc, service)
    ctx_poll_2 = build_service_ctx(ServiceAction.POLL, acc, usvc, service)
    assert ctx_poll_1["idempotency_key"] != ctx_poll_2["idempotency_key"]
    assert ctx_poll_1["idempotency_key"].startswith("usvc:10:poll:")


def test_clamp_poll_config_bounds():
    cfg = _clamp_poll_config({"interval_sec": 1, "max_attempts": 9999, "backoff": "weird"})
    assert cfg["interval_sec"] == 5
    assert cfg["max_attempts"] == 60
    assert cfg["backoff"] == "fixed"
    assert cfg["action"] == "poll"

    cfg2 = _clamp_poll_config({"interval_sec": 1000, "max_attempts": 0, "backoff": "exponential"})
    assert cfg2["interval_sec"] == 300
    assert cfg2["max_attempts"] == 1
    assert cfg2["backoff"] == "exponential"


@pytest.mark.asyncio
async def test_deliver_enters_provisioning_and_schedules_poll(monkeypatch):
    scheduled = []

    async def _fake_sched(session, usvc_id, run_at):
        scheduled.append((usvc_id, run_at))

    monkeypatch.setattr("models.user_services.schedule_provision_poll", _fake_sched)

    class _ProvIssuer:
        async def issue(self, usvc, service, acc):
            usvc.status = UsvcStatus.PROVISIONING
            usvc.private_data = {
                "_provisioning": {
                    "action": "poll",
                    "interval_sec": 10,
                    "max_attempts": 5,
                    "backoff": "fixed",
                    "attempts": 0,
                    "deadline_at": (utc_now() + timedelta(minutes=10)).isoformat(),
                }
            }

    monkeypatch.setattr("models.user_services.get_issuer", lambda *a, **kw: _ProvIssuer())

    usvc = SimpleNamespace(
        id=55,
        status=UsvcStatus.PENDING,
        price=Decimal("500.00"),
        duration=86400,
        expires_at=None,
        private_data={},
        public_data={},
        delivered_at=None,
        error=None,
        delivery_attempts=0,
    )
    service = SimpleNamespace(id=3, delivery=Delivery.LUA)
    acc = SimpleNamespace(id=7)

    mngr = UserServicesMngr(_FakeSession(), AsyncMock())
    await mngr.deliver(usvc, service, acc)

    assert usvc.status == UsvcStatus.PROVISIONING
    assert usvc.delivered_at is None
    assert usvc.expires_at is None
    assert len(scheduled) == 1
    assert scheduled[0][0] == 55


@pytest.mark.asyncio
async def test_exec_svc_provision_poll_completes_and_schedules_expire(monkeypatch):
    sched_expire = []
    monkeypatch.setattr(
        "services.billing_executor.schedule_service_expire",
        AsyncMock(side_effect=lambda s, uid, dt: sched_expire.append((uid, dt))),
    )
    monkeypatch.setattr(
        "services.billing_executor.lock_account",
        AsyncMock(return_value=SimpleNamespace(id=7, balance=Decimal("0"), bonus_balance=Decimal("0"))),
    )
    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())

    usvc = SimpleNamespace(
        id=77,
        account_id=7,
        service_id=3,
        status=UsvcStatus.PROVISIONING,
        price=Decimal("300.00"),
        duration=3600,
        expires_at=None,
        delivered_at=None,
        error=None,
        private_data={
            "_provisioning": {
                "action": "poll",
                "interval_sec": 10,
                "max_attempts": 5,
                "backoff": "fixed",
                "attempts": 0,
                "deadline_at": (utc_now() + timedelta(minutes=10)).isoformat(),
            }
        },
        public_data={},
    )
    service = SimpleNamespace(id=3, delivery=Delivery.LUA)
    session = _FakeSession({("UserServicesModel", 77): usvc, ("ServiceModel", 3): service})

    class _FakeMngr:
        async def run_action(self, u, s, a, action):
            assert action == "poll"
            u.status = UsvcStatus.ACTIVE
            u.private_data = {}

        @staticmethod
        def _apply_default_expiry(u):
            u.expires_at = utc_now() + timedelta(seconds=u.duration)

        async def _credit_referral(self, a, s, p):
            pass

    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    monkeypatch.setattr(executor, "_usvc_mngr", AsyncMock(return_value=_FakeMngr()))

    await executor.exec_svc_provision_poll(session, 77)
    assert usvc.status == UsvcStatus.ACTIVE
    assert usvc.delivered_at is not None
    assert usvc.expires_at is not None
    assert len(sched_expire) == 1
    assert sched_expire[0][0] == 77


@pytest.mark.asyncio
async def test_exec_svc_provision_poll_timeout_compensates(monkeypatch):
    monkeypatch.setattr(
        "services.billing_executor.lock_account",
        AsyncMock(return_value=SimpleNamespace(id=7, balance=Decimal("10.00"), bonus_balance=Decimal("5.00"))),
    )
    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())

    usvc = SimpleNamespace(
        id=88,
        account_id=7,
        service_id=3,
        status=UsvcStatus.PROVISIONING,
        price=Decimal("200.00"),
        delivery_attempts=0,
        private_data={
            "charged_bonus": "50.00",
            "charged_balance": "150.00",
            "_provisioning": {
                "action": "poll",
                "interval_sec": 10,
                "max_attempts": 3,
                "backoff": "fixed",
                "attempts": 3,
                "deadline_at": (utc_now() + timedelta(minutes=10)).isoformat(),
            },
        },
        error=None,
    )
    acc = SimpleNamespace(id=7, balance=Decimal("10.00"), bonus_balance=Decimal("5.00"))
    monkeypatch.setattr("services.billing_executor.lock_account", AsyncMock(return_value=acc))
    session = _FakeSession({("UserServicesModel", 88): usvc})

    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    await executor.exec_svc_provision_poll(session, 88)

    assert usvc.status == UsvcStatus.FAILED
    assert usvc.error == "provisioning timed out"
    assert "_provisioning" not in usvc.private_data
    assert acc.balance == Decimal("160.00")
    assert acc.bonus_balance == Decimal("55.00")


@pytest.mark.asyncio
async def test_exec_svc_expire_handles_stopped_service(monkeypatch):
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    usvc = SimpleNamespace(
        id=99,
        account_id=7,
        service_id=3,
        status=UsvcStatus.STOPPED,
        expires_at=past,
    )
    service = SimpleNamespace(id=3)
    acc = SimpleNamespace(id=7)
    session = _FakeSession(
        {("UserServicesModel", 99): usvc, ("ServiceModel", 3): service, ("UserModel", 7): acc}
    )

    expired_calls = []

    class _FakeMngr:
        async def expire(self, u, s, a):
            expired_calls.append(u.id)
            u.status = UsvcStatus.EXPIRED

    monkeypatch.setattr("services.billing_executor.audit", AsyncMock())
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
    )
    executor = BillingExecutor(AsyncMock(), cfg)
    monkeypatch.setattr(executor, "_usvc_mngr", AsyncMock(return_value=_FakeMngr()))

    await executor.exec_svc_expire(session, 99)
    assert expired_calls == [99]
    assert usvc.status == UsvcStatus.EXPIRED
