"""Интеграционные тесты биллинга: каталог, заказы, доставка, платежи, колбэк."""

import pytest
from sqlalchemy import text

from conftest import wait_until

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CALLBACK_SECRET = "test-callback-secret"


async def _auth(http, new_user):
    login, pwd, tokens = await new_user()
    return login, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_catalog_lists_seeded_service(http, seed):
    sid = await seed.key_service()
    r = await http.get("/api/v1/catalog/services")
    assert r.status_code == 200, r.text
    assert any(s["id"] == sid for s in r.json()["items"])


async def test_order_key_delivery(http, new_user, seed, engine):
    sid = await seed.key_service(price="10.00", keys=2)
    login, hdr = await _auth(http, new_user)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )

    r = await http.post(
        "/api/v1/user/services/create", json={"service_id": sid}, headers=hdr
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "delivered"
    assert "key" in body["public_data"]


async def test_order_lua_delivery_runs_script(http, new_user, seed, engine):
    sid = await seed.lua_service(price="5.00")
    login, hdr = await _auth(http, new_user)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )

    r = await http.post(
        "/api/v1/user/services/create", json={"service_id": sid}, headers=hdr
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "delivered"
    # demo_service.lua читает service.params.message == "hi"
    assert body["public_data"].get("message") == "hi"


async def test_service_expiry_via_billing_loop(http, new_user, seed, engine):
    sid = await seed.lua_service_timed(price="5.00", duration=2)
    login, hdr = await _auth(http, new_user)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )

    r = await http.post(
        "/api/v1/user/services/create", json={"service_id": sid}, headers=hdr
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "delivered"
    assert body["state"] == "active"
    assert body["expires_at"] is not None
    usvc_id = body["id"]

    async def _state():
        async with engine.begin() as c:
            return await c.scalar(
                text("SELECT state FROM user_services WHERE id=:i"), {"i": usvc_id}
            )

    # billing-loop должен пометить услугу истёкшей после наступления expires_at.
    await wait_until(_state, lambda s: s == "expired", timeout=30, interval=1)

    sid = await seed.key_service(price="10.00", keys=1)
    _, hdr = await _auth(http, new_user)
    r = await http.post(
        "/api/v1/user/services/create", json={"service_id": sid}, headers=hdr
    )
    # нет баланса -> ошибка (402/400/409 в зависимости от реализации)
    assert r.status_code >= 400
    assert r.status_code != 500


async def test_payment_topup_and_callback(http, new_user, seed):
    provider = await seed.pay_provider(secret=CALLBACK_SECRET)
    _, hdr = await _auth(http, new_user)

    r = await http.post(
        "/api/v1/user/purchases/create",
        json={
            "amount": "40.00",
            "provider": provider,
            "target": "balance",
            "return_url": "https://x.test/d",
        },
        headers=hdr,
    )
    assert r.status_code in (200, 201), r.text
    payment = r.json()
    assert payment["status"] == "pending"
    # init-скрипт положил ссылку оплаты в public_data.
    assert payment["public_data"].get("pay_url")
    pid = payment["id"]

    r = await http.post(
        f"/api/v1/callback/payment/{provider}",
        json={"payment_id": pid, "success": True, "sign": CALLBACK_SECRET},
    )
    assert r.status_code == 200, r.text

    async def _fetch_status():
        resp = await http.get("/api/v1/user/purchases", headers=hdr)
        resp.raise_for_status()
        row = next((p for p in resp.json()["items"] if p["id"] == pid), None)
        return row and row["status"]

    status_val = await wait_until(_fetch_status, lambda s: s == "paid", timeout=30)
    assert status_val == "paid"


async def test_callback_bad_signature_rejected(http, new_user, seed):
    provider = await seed.pay_provider(secret=CALLBACK_SECRET)
    _, hdr = await _auth(http, new_user)
    r = await http.post(
        "/api/v1/user/purchases/create",
        json={"amount": "10.00", "provider": provider, "target": "balance"},
        headers=hdr,
    )
    pid = r.json()["id"]
    r = await http.post(
        f"/api/v1/callback/payment/{provider}",
        json={"payment_id": pid, "success": True, "sign": "deadbeef"},
    )
    assert r.status_code == 401
