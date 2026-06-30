"""Интеграционные тесты биллинга: заказы, доставка, пополнения, колбэк."""

import hashlib
import hmac
import os

import pytest

CALLBACK_SECRET = os.environ.get("PAY_CALLBACK_SECRET", "test-callback-secret")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _sign(topup_id: int, external_id: str, success: bool) -> str:
    raw = f"{topup_id}:{external_id}:{int(success)}".encode()
    return hmac.new(CALLBACK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


async def _auth(http, new_user):
    login, pwd, tokens = await new_user()
    return login, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_catalog_lists_seeded_service(http, new_user, seed):
    sid = await seed.key_service()
    _, hdr = await _auth(http, new_user)
    r = await http.get("/api/v1/services", headers=hdr)
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())


async def test_order_key_delivery(http, new_user, seed, engine):
    sid = await seed.key_service(price="10.00", keys=2)
    login, hdr = await _auth(http, new_user)
    # начислим баланс, чтобы хватило на заказ
    from sqlalchemy import text

    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )

    r = await http.post("/api/v1/orders", json={"service_id": sid}, headers=hdr)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "delivered"
    assert "key" in body["public_data"]


async def test_order_lua_delivery_runs_script(http, new_user, seed, engine):
    sid = await seed.lua_service(price="5.00")
    login, hdr = await _auth(http, new_user)
    from sqlalchemy import text

    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )

    r = await http.post("/api/v1/orders", json={"service_id": sid}, headers=hdr)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["status"] == "delivered"
    # demo_service.lua читает service.params.message == "hi"
    assert body["public_data"].get("message") == "hi"


async def test_insufficient_balance_rejected(http, new_user, seed):
    sid = await seed.key_service(price="10.00", keys=1)
    _, hdr = await _auth(http, new_user)
    r = await http.post("/api/v1/orders", json={"service_id": sid}, headers=hdr)
    # нет баланса -> ошибка (402/400/409 в зависимости от реализации)
    assert r.status_code >= 400
    assert r.status_code != 500


async def test_topup_and_signed_callback(http, new_user, seed):
    provider = await seed.payment_script()
    _, hdr = await _auth(http, new_user)

    r = await http.post(
        "/api/v1/topups",
        json={
            "amount": "40.00",
            "provider": provider,
            "return_url": "https://x.test/d",
        },
        headers=hdr,
    )
    assert r.status_code in (200, 201), r.text
    topup = r.json()
    assert topup["status"] == "pending"
    topup_id = topup["id"]

    external_id = await seed.topup_external_id(topup_id)
    assert external_id

    r = await http.post(
        "/api/v1/callback/payment",
        json={
            "topup_id": topup_id,
            "external_id": external_id,
            "success": True,
            "sign": _sign(topup_id, external_id, True),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"


async def test_callback_bad_signature_rejected(http, new_user, seed):
    provider = await seed.payment_script()
    _, hdr = await _auth(http, new_user)
    r = await http.post(
        "/api/v1/topups",
        json={"amount": "10.00", "provider": provider},
        headers=hdr,
    )
    topup_id = r.json()["id"]
    r = await http.post(
        "/api/v1/callback/payment",
        json={
            "topup_id": topup_id,
            "external_id": "forged",
            "success": True,
            "sign": "deadbeef",
        },
    )
    assert r.status_code == 401
