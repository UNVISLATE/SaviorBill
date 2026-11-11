"""Юнит-тесты Фазы 2: финансовая логика, промокоды, рефанды, FX/комиссия и edge-cases."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.v1.auth.claim import verify_claim_code
from api.v1.internal.service_keys import import_keys_internal, require_lua_token
from dependencies.auth import get_current_acc
from dependencies.payment import PayMngr
from enums import Delivery, PayStatus, PayTarget, PriceType, UsvcStatus
from errors import AuthSessionLimitError
from lifecycle.delivery.provider.key_service import KeyService
from lua.integrations.delivery import LuaService
from lua.schemas import LuaRequest
from middleware.request_tracker import _extract_user_telemetry
from models.user_services import UserServicesMngr
from schemas.manifest import FieldCondition, FieldDefinition, FieldOption, FieldType, ScriptManifest
from services.billing_loop import BillingLoop
from services.manifest import validate_client_order_form
from services.pricing import resolve_service_order

pytestmark = pytest.mark.unit


# ── 2.1: _charge с amount <= 0 не должен падать на распаковке ─────────────────


def test_charge_zero_returns_zero_tuple():
    acc = SimpleNamespace(bonus_balance=Decimal("10.00"), balance=Decimal("25.00"))
    res = UserServicesMngr._charge(acc, Decimal("0.00"))
    assert res == (Decimal("0"), Decimal("0"))
    assert acc.bonus_balance == Decimal("10.00")
    assert acc.balance == Decimal("25.00")


@pytest.mark.asyncio
async def test_create_service_with_full_discount_succeeds(monkeypatch):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    monkeypatch.setattr("models.user_services.lock_account", AsyncMock())

    acc = SimpleNamespace(id=1, bonus_balance=Decimal("0"), balance=Decimal("0"))
    service = SimpleNamespace(
        id=10,
        price=Decimal("100.00"),
        price_type=PriceType.FIXED,
        pricing_config=None,
        duration=3600,
        params={},
        actions=[],
        settings={},
        delivery=Delivery.KEY,
    )
    mngr = UserServicesMngr(session, bus=None)
    monkeypatch.setattr(mngr, "deliver", AsyncMock())

    usvc = await mngr.create(acc, service, discount=Decimal("100.00"), charge=True, deliver=True)
    assert usvc.price == Decimal("0.00")
    assert usvc.private_data["charged_bonus"] == "0"
    assert usvc.private_data["charged_balance"] == "0"


# ── 2.2: deliver() и run_action() сохраняют private_data (promocode_id) ──────


@pytest.mark.asyncio
async def test_key_service_issue_preserves_existing_private_data(monkeypatch):
    key = SimpleNamespace(id=55, value="SECRET-KEY", is_used=False, order_id=None, used_at=None)
    session = SimpleNamespace(scalar=AsyncMock(return_value=key))
    usvc = SimpleNamespace(
        id=7,
        private_data={"promocode_id": 99, "charged_bonus": "0"},
        public_data={},
        digikey_id=None,
    )
    service = SimpleNamespace(id=3)
    acc = SimpleNamespace(id=1)

    monkeypatch.setattr("services.catalog_cache.invalidate_service_entity", AsyncMock())
    await KeyService(session).issue(usvc, service, acc)

    assert usvc.private_data["digikey_id"] == 55
    assert usvc.private_data["promocode_id"] == 99
    assert usvc.private_data["charged_bonus"] == "0"


@pytest.mark.asyncio
async def test_lua_service_run_action_merges_public_and_private_data(monkeypatch):
    session = SimpleNamespace(get=AsyncMock())
    script = SimpleNamespace(id=5, is_active=True, kind="service")
    session.get = AsyncMock(return_value=script)

    monkeypatch.setattr(
        "models.system_scripts.resolve_version",
        AsyncMock(return_value=("svc.lua", 2)),
    )

    class _DummyRunner:
        def __init__(self, bus):
            pass

        async def run_service(self, *a, **kw):
            return {
                "public": {"ip": "1.2.3.4"},
                "private": {"vm_id": "abc"},
                "state": UsvcStatus.ACTIVE,
            }

    monkeypatch.setattr("lua.integrations.delivery.LuaRunner", _DummyRunner)

    usvc = SimpleNamespace(
        id=7,
        payment_id=None,
        public_data={"existing_pub": "keep"},
        private_data={"promocode_id": 42},
        lua_script_version=1,
        status=UsvcStatus.PENDING,
        expires_at=None,
    )
    service = SimpleNamespace(id=3, lua_script_id=5, lua_script_version=None)
    acc = SimpleNamespace(id=1)

    await LuaService(session, bus=object()).run_action(usvc, service, acc, "renew")

    assert usvc.public_data == {"existing_pub": "keep", "ip": "1.2.3.4"}
    assert usvc.private_data == {"promocode_id": 42, "vm_id": "abc"}


@pytest.mark.asyncio
async def test_pay_mngr_settle_reads_promocode_id_before_deliver(monkeypatch):
    usvc = SimpleNamespace(
        id=11,
        service_id=4,
        payment_id=None,
        private_data={"promocode_id": 77},
        status=UsvcStatus.PENDING,
    )
    service = SimpleNamespace(id=4)
    acc = SimpleNamespace(id=1, balance=Decimal("0"))

    session = AsyncMock()

    async def _get(model, pk):
        if model.__name__ == "UserServicesModel":
            return usvc
        if model.__name__ == "ServiceModel":
            return service
        return None

    session.get = AsyncMock(side_effect=_get)
    monkeypatch.setattr("dependencies.payment.lock_account", AsyncMock(return_value=acc))

    async def _clobber_deliver(u, _s, _a):
        # Симулируем ситуацию, если issuer заменил private_data без promocode_id
        u.private_data = {"digikey_id": 9}
        u.status = UsvcStatus.ACTIVE

    monkeypatch.setattr(
        "dependencies.payment.UserServicesMngr.deliver",
        AsyncMock(side_effect=_clobber_deliver),
    )

    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())
    mngr._redeem_promo = AsyncMock()
    mngr._credited_amount = AsyncMock(return_value=Decimal("100.00"))
    mngr._audit_balance_topup = AsyncMock()

    payment = SimpleNamespace(
        id=1,
        account_id=1,
        target=PayTarget.SERVICE,
        user_svc_id=11,
        currency="RUB",
        amount=Decimal("100.00"),
        base_amount=Decimal("100.00"),
        fx_rate=Decimal("1"),
        status=PayStatus.PENDING,
        paid_at=None,
        external_id=None,
    )

    await mngr._settle(payment, {"paid": True, "paid_amount": ""})
    mngr._redeem_promo.assert_awaited_once_with(77, payment, usvc)


# ── 2.3 & 2.4 & 2.9 PayMngr callback refund + credited_amount + edge-cases ──


@pytest.mark.asyncio
async def test_pay_mngr_callback_processes_refund_on_paid_payment():
    payment = SimpleNamespace(
        id=5,
        status=PayStatus.PAID,
        public_data={},
        private_data={},
        lua_script_version=1,
    )
    session = AsyncMock()
    mngr = PayMngr(session, bus=MagicMock(), box=MagicMock())
    mngr._provider = AsyncMock(return_value=SimpleNamespace(slug="test", script_version=1))
    mngr._script = AsyncMock(return_value=(SimpleNamespace(), "pay.lua", 1))
    mngr._secrets = MagicMock(return_value={})
    mngr.runner = SimpleNamespace(
        run_payment=AsyncMock(return_value={"private": {"ok": True, "refunded": True, "payment_id": 5}})
    )
    mngr._locate = AsyncMock(return_value=payment)
    mngr._apply_refund = AsyncMock()
    mngr._settle = AsyncMock()

    req = LuaRequest(method="POST", ip="1.1.1.1", headers={}, query={}, body={})
    await mngr.callback("test", req)

    mngr._apply_refund.assert_awaited_once()
    mngr._settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_credited_amount_ignores_fee_and_fx_markup_inflation():
    fx = SimpleNamespace(to_base=AsyncMock(return_value=(Decimal("999.00"), Decimal("1"), "RUB")))
    mngr = PayMngr(AsyncMock(), bus=MagicMock(), box=MagicMock(), fx=fx)

    # Инвойс: 100.00 RUB к зачислению, 105.00 RUB к оплате (5% комиссия)
    payment_exact = SimpleNamespace(
        amount=Decimal("105.00"),
        base_amount=Decimal("100.00"),
        base_currency="RUB",
        currency="RUB",
        fx_rate=Decimal("1"),
    )
    assert await mngr._credited_amount(payment_exact, actual_paid=Decimal("105.00")) == Decimal("100.00")
    fx.to_base.assert_not_awaited()

    # Частичная оплата 52.50 из 105.00 -> ровно 50.00 RUB к зачислению
    payment_partial = SimpleNamespace(
        amount=Decimal("105.00"),
        base_amount=Decimal("100.00"),
        base_currency="RUB",
        currency="RUB",
        fx_rate=Decimal("1"),
    )
    assert await mngr._credited_amount(payment_partial, actual_paid=Decimal("52.50")) == Decimal("50.00")
    assert payment_partial.base_amount == Decimal("50.00")


@pytest.mark.asyncio
async def test_apply_refund_handles_zero_base_amount(monkeypatch):
    acc = SimpleNamespace(id=1, balance=Decimal("50.00"))
    monkeypatch.setattr("dependencies.payment.lock_account", AsyncMock(return_value=acc))
    mngr = PayMngr(AsyncMock(), bus=MagicMock(), box=MagicMock())
    payment = SimpleNamespace(
        id=9,
        account_id=1,
        target=PayTarget.BALANCE,
        user_svc_id=None,
        amount=Decimal("100.00"),
        base_amount=Decimal("0.00"),
        status=PayStatus.PAID,
        private_data={},
    )
    await mngr._apply_refund(payment, {})
    assert acc.balance == Decimal("50.00")
    assert payment.private_data["refund"]["deducted"] == "0.00"


# ── 2.5: Internal service keys import + constant-time token ──────────────────


@pytest.mark.asyncio
async def test_internal_service_keys_token_and_create_batch():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/internal/service-keys/import",
        "headers": [],
        "app": SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(LUA_SERVICE_TOKEN="secret-tok"))),
    }
    req = Request(scope)
    with pytest.raises(HTTPException) as exc:
        await require_lua_token(req, authorization="Bearer wrong")
    assert exc.value.status_code == 403

    await require_lua_token(req, authorization="Bearer secret-tok")

    svc = SimpleNamespace(id=4, name="Keys", delivery=Delivery.KEY)
    mngr = SimpleNamespace(
        s=SimpleNamespace(
            get=AsyncMock(return_value=svc),
            commit=AsyncMock(),
            scalar=AsyncMock(return_value=2),
        ),
        create_batch=AsyncMock(return_value=([SimpleNamespace(), SimpleNamespace()], 0)),
    )
    body = MagicMock(service="4", keys=["k1", "k2"])
    out = await import_keys_internal(body, mngr=mngr)
    assert out.imported == 2
    assert out.available_total == 2
    mngr.create_batch.assert_awaited_once_with(4, ["k1", "k2"])


# ── 2.7: BillingLoop seed pending + FxRates wiring + deliver expiry ──────────


@pytest.mark.asyncio
async def test_user_service_deliver_applies_default_expiry(monkeypatch):
    class _Issuer:
        async def issue(self, usvc, service, acc):
            pass

    monkeypatch.setattr("models.user_services.get_issuer", lambda *a, **kw: _Issuer())
    session = AsyncMock()
    mngr = UserServicesMngr(session, bus=None)
    mngr._credit_referral = AsyncMock()

    usvc = SimpleNamespace(
        status=UsvcStatus.PENDING,
        expires_at=None,
        duration=3600,
        delivered_at=None,
        error=None,
        price=Decimal("10"),
    )
    service = SimpleNamespace(delivery=Delivery.KEY)
    acc = SimpleNamespace(id=1)

    await mngr.deliver(usvc, service, acc)
    assert usvc.status == UsvcStatus.ACTIVE
    assert usvc.expires_at is not None
    assert usvc.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_billing_loop_tick_seeds_pending_and_pay_mngr_passes_deps(monkeypatch):
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=1,
        BILLING_QUEUE_KEY="billing:queue",
        BILLING_QUEUE_WINDOW=100,
        SETTINGS_CACHE_TTL=1,
        SECRETS_KEY=None,
        BILLING_PAY_RECHECK_AFTER=60,
        LUA_TASK_STREAM="lua:tasks",
        LUA_RESULT_STREAM="lua:results",
        LUA_RESULT_GROUP="billing",
        LUA_TASK_STREAM_MAXLEN=100,
        BUS_SIGNING_KEY="",
        instance_id="test-1",
    )
    loop = BillingLoop.__new__(BillingLoop)
    loop.cfg = cfg
    loop.vk = AsyncMock()
    loop.vk.set = AsyncMock(return_value=True)
    loop._claim_due = AsyncMock(return_value=[])
    loop._refill = AsyncMock()
    loop._seed_pending_payments = AsyncMock()
    loop._seed_failed_deliveries = AsyncMock()
    loop._maybe_auto_cleanup_media = AsyncMock()
    loop._dlq = SimpleNamespace(refresh_metrics=AsyncMock())

    session = AsyncMock()
    sm = MagicMock()
    sm.return_value.__aenter__.return_value = session
    loop.sm = sm

    await loop._tick()
    loop._seed_pending_payments.assert_awaited_once_with(session)

    # _pay_mngr передаёт bus, session и box в FxRates
    loop._bus = AsyncMock(return_value="bus-obj")
    loop._dispatcher = AsyncMock(return_value="disp-obj")
    monkeypatch.setattr("services.billing_loop.make_secbox", lambda _c: "box-obj")
    pm = await loop._pay_mngr(session)
    assert pm.fx.bus == "bus-obj"
    assert pm.fx.session is session
    assert pm.fx.box == "box-obj"


# ── 2.9: switch pricing, manifest depends_on, tracker user, claim 409 ────────


def test_configurable_switch_pricing_handles_bool_and_rejects_invalid():
    svc = SimpleNamespace(
        price=Decimal("100.00"),
        price_type=PriceType.CONFIGURABLE,
        duration=3600,
        settings={},
        pricing_config={
            "components": [
                {
                    "code": "ddos",
                    "type": "switch",
                    "unit_price": "50.00",
                    "default": False,
                    "path": "features.ddos",
                }
            ]
        },
    )
    res_on = resolve_service_order(svc, components={"ddos": True})
    assert res_on.price == Decimal("150.00")
    assert res_on.effective_settings == {"features": {"ddos": True}}
    assert res_on.order_config["components"]["ddos"]["price_delta"] == "50.00"

    res_off = resolve_service_order(svc, components={"ddos": "false"})
    assert res_off.price == Decimal("100.00")
    assert res_off.effective_settings == {"features": {"ddos": False}}

    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, components={"ddos": "not-a-bool"})
    assert exc.value.status_code == 400


def test_manifest_depends_on_supports_in_not_in_and_case_insensitive_bool():
    manifest = ScriptManifest(
        name="Cond",
        slug="cond",
        client_order_form=[
            FieldDefinition(
                id="mode",
                type=FieldType.SELECT,
                label="Mode",
                required=True,
                options=[
                    FieldOption(value="a", label="A"),
                    FieldOption(value="b", label="B"),
                    FieldOption(value="c", label="C"),
                ],
            ),
            FieldDefinition(
                id="dedicated",
                type=FieldType.TOGGLE,
                label="Dedicated",
                default=False,
            ),
            FieldDefinition(
                id="region_note",
                type=FieldType.TEXT,
                label="Note",
                required=True,
                depends_on=FieldCondition(field="mode", **{"in": ["a", "b"]}),
            ),
            FieldDefinition(
                id="dedicated_ip",
                type=FieldType.TEXT,
                label="IP",
                required=True,
                depends_on=FieldCondition(field="dedicated", equals="true"),
            ),
        ],
    )
    clean = validate_client_order_form(
        manifest,
        {"mode": "b", "dedicated": True, "region_note": "ok", "dedicated_ip": "1.2.3.4"},
    )
    assert clean["region_note"] == "ok"
    assert clean["dedicated_ip"] == "1.2.3.4"

    # mode='c' не входит в ['a', 'b'], dedicated=False -> зависимые required поля пропускаются
    clean_skip = validate_client_order_form(manifest, {"mode": "c", "dedicated": False})
    assert "region_note" not in clean_skip
    assert "dedicated_ip" not in clean_skip


@pytest.mark.asyncio
async def test_request_tracker_extracts_user_attached_by_get_current_acc():
    acc = SimpleNamespace(id=77, login="alice", role=SimpleNamespace(name="admin"))
    mngr = SimpleNamespace(by_id=AsyncMock(return_value=acc))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/user/me",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    jwt_public_keys=lambda: {"kid1": "pub"},
                    JWT_ALG="RS256",
                    JWT_ISS="saviorbill",
                )
            )
        ),
    }
    req = Request(scope)

    from security.sec import jwt as jwtu

    monkeypatch_orig = jwtu.decode_jwt
    try:
        jwtu.decode_jwt = lambda *a, **kw: SimpleNamespace(typ=jwtu.ACCESS, sub="77", extra={})
        got = await get_current_acc(req, cred=SimpleNamespace(credentials="tok"), mngr=mngr)
        assert got is acc
        assert _extract_user_telemetry(req) == (77, "alice", "admin")
    finally:
        jwtu.decode_jwt = monkeypatch_orig


@pytest.mark.asyncio
async def test_claim_verify_maps_session_limit_error_to_409():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/claim-guest-account/verify",
        "headers": [],
    }
    req = Request(scope)
    resp = MagicMock()
    svc = SimpleNamespace(
        verify_guest_claim=AsyncMock(return_value=SimpleNamespace(id=1)),
        s=SimpleNamespace(commit=AsyncMock()),
    )
    tokens = SimpleNamespace(
        issue_tracked=AsyncMock(side_effect=AuthSessionLimitError("limit")),
        cfg=SimpleNamespace(),
    )
    body = SimpleNamespace(claim_token="tok", code="123456", password="password123")

    with pytest.raises(HTTPException) as exc:
        await verify_claim_code(body, req, resp, svc=svc, tokens=tokens)
    assert exc.value.status_code == 409
