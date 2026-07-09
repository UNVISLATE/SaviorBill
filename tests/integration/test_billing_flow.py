"""Интеграционные тесты биллинга: каталог, заказы, доставка, платежи, колбэк."""

import pytest
from sqlalchemy import text

from conftest import uniq, wait_until

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


async def test_services_json_columns_default_when_omitted(engine):
    """Регресс: params/settings должны получать серверный дефолт '{}',

    а не падать NotNullViolationError, если insert их не указывает явно
    (как это делают часть сидеров/внешних скриптов).
    """
    slug = uniq("bare_svc")
    async with engine.begin() as c:
        row = await c.execute(
            text(
                "INSERT INTO services (slug,name,price,currency,delivery,is_active) "
                "VALUES (:slug,'Bare svc','1.00','RUB','key',true) "
                "RETURNING params, settings, actions"
            ),
            {"slug": slug},
        )
        params, settings, actions = row.one()
    assert params == {}
    assert settings == {}
    assert actions == []


async def test_promo_catalog_conditions_defaults_when_omitted(engine):
    """Регресс: promo_catalogs.conditions тоже должен иметь серверный дефолт."""
    slug = uniq("bare_cat")
    async with engine.begin() as c:
        row = await c.execute(
            text(
                "INSERT INTO promo_catalogs (name,slug,kind,value,is_active) "
                "VALUES ('Bare cat',:slug,'bonus','1.00',true) "
                "RETURNING conditions"
            ),
            {"slug": slug},
        )
        (conditions,) = row.one()
    assert conditions == {}


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
    assert body["status"] == "active"
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
    assert body["status"] == "active"
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
    assert body["status"] == "active"
    assert body["expires_at"] is not None
    usvc_id = body["id"]

    async def _state():
        async with engine.begin() as c:
            return await c.scalar(
                text("SELECT status FROM user_services WHERE id=:i"), {"i": usvc_id}
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


async def test_referral_bonus_credited_on_service_purchase(
    http, new_user, seed, engine
):
    # Реферер регистрируется и получает свой ref_code.
    _, _, ref_tokens = await new_user()
    ref_hdr = {"Authorization": f"Bearer {ref_tokens['access_token']}"}
    me = await http.get("/api/v1/user/me", headers=ref_hdr)
    me.raise_for_status()
    ref_code = me.json()["ref_code"]
    assert ref_code

    # Глобальный процент отчислений реферреру = 10%.
    async with engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO settings (key,value,is_secret) VALUES "
                "('referral.percent','10',false) "
                "ON CONFLICT (key) DO UPDATE SET value='10'"
            )
        )

    # Приглашённый пользователь регистрируется по коду и покупает услугу.
    sid = await seed.key_service(price="10.00", keys=1)
    login, _, _ = await new_user(ref_code)
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE accounts SET balance=100 WHERE login=:l"), {"l": login}
        )
        referrer_id = await c.scalar(
            text("SELECT id FROM accounts WHERE ref_code=:c"), {"c": ref_code}
        )
        invited_ref = await c.scalar(
            text("SELECT referred_by FROM accounts WHERE login=:l"), {"l": login}
        )
    assert invited_ref == referrer_id

    r = await http.post(
        "/api/v1/auth/login", json={"login": login, "password": "secret123"}
    )
    r.raise_for_status()
    inv_hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await http.post(
        "/api/v1/user/services/create", json={"service_id": sid}, headers=inv_hdr
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["status"] == "active"

    # Рефереру начислено 10% от 10.00 = 1.00 на бонусный баланс.
    async with engine.begin() as c:
        bonus = await c.scalar(
            text("SELECT bonus_balance FROM accounts WHERE id=:i"),
            {"i": referrer_id},
        )
    assert str(bonus) == "1.00"
