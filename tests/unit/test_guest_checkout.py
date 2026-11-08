"""Юнит-тесты гостевого чекаута, клейма аккаунтов и авто-апгрейда через OAuth."""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from enums import BaseRole
from models.roles import Role
from models.user import UserModel
from services.guest_checkout import (
    GuestCheckoutSvc,
    mask_email,
    _CLAIM_MAX_FAILS,
    _CLAIM_PREFIX,
    _CLAIM_CODE_PREFIX,
    _CLAIM_FAIL_PREFIX,
    _ORDER_TOKEN_PREFIX,
)
from security.sec.pwd import verify_pass

pytestmark = pytest.mark.unit


class _FakeValkey:
    def __init__(self) -> None:
        self._vals: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._vals[key] = value
        if ex is not None:
            self._ttls[key] = ex

    async def get(self, key: str) -> str | None:
        return self._vals.get(key)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._vals.pop(k, None)
            self._ttls.pop(k, None)

    async def incr(self, key: str) -> int:
        cur = int(self._vals.get(key, "0")) + 1
        self._vals[key] = str(cur)
        return cur

    async def expire(self, key: str, seconds: int) -> None:
        self._ttls[key] = seconds


class _FakeSettings:
    def __init__(self, settings_dict: dict | None = None) -> None:
        self._d = settings_dict or {}

    async def get(self, key: str, default: str | None = None) -> str | None:
        return str(self._d.get(key, default))

    async def get_int(self, key: str, default: int | None = None) -> int:
        return int(self._d.get(key, default))

    async def get_bool(self, key: str, default: bool | None = None) -> bool:
        v = self._d.get(key, default)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("1", "true", "yes", "on")


class TestMaskEmail:
    def test_masks_standard_email(self) -> None:
        assert mask_email("ivan@gmail.com") == "i***n@gmail.com"

    def test_masks_short_username(self) -> None:
        assert mask_email("ab@domain.com") == "a***@domain.com"
        assert mask_email("a@domain.com") == "a***@domain.com"

    def test_masks_invalid_empty(self) -> None:
        assert mask_email("") == "***"
        assert mask_email("no_at_sign") == "***"


class TestOrderViewToken:
    @pytest.mark.asyncio
    async def test_create_and_read_order_token(self) -> None:
        vk = _FakeValkey()
        settings = _FakeSettings({"shop.guest.order_token_ttl": 3600})
        svc = GuestCheckoutSvc(
            session=AsyncMock(), vk=vk, sender=AsyncMock(), settings=settings
        )

        token = await svc.create_order_view_token(
            order_id=42, payment_id=101, account_id=5, requires_auth=False
        )
        assert isinstance(token, str) and len(token) >= 16

        payload = await svc.get_order_token_payload(token)
        assert payload is not None
        assert payload["order_id"] == 42
        assert payload["payment_id"] == 101
        assert payload["account_id"] == 5
        assert payload["requires_auth"] is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_token_returns_none(self) -> None:
        vk = _FakeValkey()
        svc = GuestCheckoutSvc(
            session=AsyncMock(), vk=vk, sender=AsyncMock(), settings=_FakeSettings()
        )
        assert await svc.get_order_token_payload("invalid_token") is None


class TestGuestClaimFlow:
    @pytest.mark.asyncio
    async def test_request_claim_fails_for_nonexistent_or_registered_user(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        vk = _FakeValkey()
        svc = GuestCheckoutSvc(
            session=session, vk=vk, sender=AsyncMock(), settings=_FakeSettings()
        )

        # 1. Пользователь не существует
        with patch("models.user.UserMngr.by_email", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await svc.request_guest_claim("unknown@gmail.com")
            assert exc.value.status_code == 400

        # 2. Пользователь уже в роли USER (не гость)
        registered_user = UserModel(id=1, email="user@gmail.com")
        registered_user.role = Role(id=2, key=BaseRole.USER, name="User")
        with patch("models.user.UserMngr.by_email", AsyncMock(return_value=registered_user)):
            with pytest.raises(HTTPException) as exc:
                await svc.request_guest_claim("user@gmail.com")
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_claim_success_for_guest(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        vk = _FakeValkey()
        sender = AsyncMock()
        sender.send_template = AsyncMock(return_value=True)

        guest_user = UserModel(id=10, login="guest:123", email="guest@gmail.com")
        guest_user.role = Role(id=1, key=BaseRole.GUEST, name="Guest")

        svc = GuestCheckoutSvc(
            session=session, vk=vk, sender=sender, settings=_FakeSettings({"shop.guest.claim_code_ttl": 600})
        )

        with patch("models.user.UserMngr.by_email", AsyncMock(return_value=guest_user)):
            claim_token, ttl = await svc.request_guest_claim("guest@gmail.com")

        assert len(claim_token) >= 16
        assert ttl == 600

        # Проверяем, что в Valkey сохранены нагрузка и 6-значный код
        raw_payload = await vk.get(_CLAIM_PREFIX + claim_token)
        assert raw_payload is not None
        payload = json.loads(raw_payload)
        assert payload["account_id"] == 10
        assert payload["email"] == "guest@gmail.com"

        code = await vk.get(_CLAIM_CODE_PREFIX + claim_token)
        assert code is not None
        assert len(code) == 6 and code.isdigit()

        # Проверяем, что письмо отправлено
        sender.send_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_claim_wrong_code_and_lockout(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        vk = _FakeValkey()
        svc = GuestCheckoutSvc(
            session=session, vk=vk, sender=AsyncMock(), settings=_FakeSettings()
        )

        claim_token = "claim_tok_123456789"
        await vk.set(_CLAIM_PREFIX + claim_token, json.dumps({"account_id": 10, "email": "g@ya.ru"}))
        await vk.set(_CLAIM_CODE_PREFIX + claim_token, "123456")

        # 4 неверных попытки
        for _ in range(4):
            with pytest.raises(HTTPException) as exc:
                await svc.verify_guest_claim(claim_token, "000000", "NewPass1234!")
            assert exc.value.status_code == 400
            assert "invalid" in exc.value.detail

        assert await vk.get(_CLAIM_PREFIX + claim_token) is not None

        # 5-я неверная попытка — сгорание заявки
        with pytest.raises(HTTPException) as exc:
            await svc.verify_guest_claim(claim_token, "000000", "NewPass1234!")
        assert exc.value.status_code == 400

        # После 5 попыток ключи удалены
        assert await vk.get(_CLAIM_PREFIX + claim_token) is None
        assert await vk.get(_CLAIM_CODE_PREFIX + claim_token) is None

    @pytest.mark.asyncio
    async def test_verify_claim_success_upgrades_to_user_and_sets_argon2_password(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        vk = _FakeValkey()

        guest_user = UserModel(id=10, login="guest:123", email="g@ya.ru", pass_hash=None)
        guest_user.role = Role(id=1, key=BaseRole.GUEST, name="Guest")
        session.get = AsyncMock(return_value=guest_user)

        user_role = Role(id=2, key=BaseRole.USER, name="User")

        svc = GuestCheckoutSvc(
            session=session, vk=vk, sender=AsyncMock(), settings=_FakeSettings()
        )

        claim_token = "claim_tok_valid_test_123"
        await vk.set(_CLAIM_PREFIX + claim_token, json.dumps({"account_id": 10, "email": "g@ya.ru"}))
        await vk.set(_CLAIM_CODE_PREFIX + claim_token, "654321")

        with patch("models.user.UserMngr.role_by_key", AsyncMock(return_value=user_role)):
            acc = await svc.verify_guest_claim(claim_token, "654321", "MySecurePassword123!")

        assert acc.role.key == BaseRole.USER
        assert acc.role_id == user_role.id
        assert acc.pass_hash is not None
        assert verify_pass(acc.pass_hash, "MySecurePassword123!")

        # Ключи очищены после успешного клейма
        assert await vk.get(_CLAIM_PREFIX + claim_token) is None
        assert await vk.get(_CLAIM_CODE_PREFIX + claim_token) is None


class TestOAuthAutoUpgradeGuest:
    @pytest.mark.asyncio
    async def test_oauth_verified_email_auto_upgrades_guest_to_user(self) -> None:
        from dependencies.oauth import OAuthSvc
        from schemas.oauth import OAuthUser

        session = AsyncMock()
        session.add = MagicMock()
        vk = _FakeValkey()

        guest_user = UserModel(id=15, login="guest:abc", email="ivan@gmail.com")
        guest_user.role = Role(id=1, key=BaseRole.GUEST, name="Guest")

        # Mock scalar to return guest_user for email lookup
        session.scalar = AsyncMock(side_effect=[
            None,        # UserOauthModel lookup (not yet linked)
            guest_user,  # UserModel lookup by email
        ])

        user_role = Role(id=2, key=BaseRole.USER, name="User")

        svc = OAuthSvc(
            session=session,
            vk=vk,
            bus=AsyncMock(),
            cfg=SimpleNamespace(PUBLIC_URL="http://test.local"),
            box=AsyncMock(),
            sender=AsyncMock(),
            settings=_FakeSettings(),
        )

        oauth_user = OAuthUser(
            sub="google_sub_123",
            email="ivan@gmail.com",
            email_verified=True,
            name="Ivan",
            picture=None,
            raw={},
        )

        with patch("models.user.UserMngr.role_by_key", AsyncMock(return_value=user_role)):
            acc, pending = await svc.link_account("google", oauth_user)

        assert pending is None
        assert acc is not None
        assert acc.id == 15
        assert acc.role.key == BaseRole.USER
        assert acc.role_id == user_role.id


class TestPublicPurchasesEndpoint:
    @pytest.mark.asyncio
    async def test_guest_checkout_disabled_raises_403(self) -> None:
        from api.v1.public import create_guest_purchase
        from schemas.guest import GuestPurchaseCreate

        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(cors_origins_list=[], PUBLIC_URL="http://test.local"))))
        body = GuestPurchaseCreate(email="guest@ya.ru", provider="stripe", service_id=1)
        settings = _FakeSettings({"shop.guest_checkout.enabled": False})

        with pytest.raises(HTTPException) as exc:
            await create_guest_purchase(
                request=req,
                body=body,
                session=AsyncMock(),
                settings=settings,
                guest_svc=AsyncMock(),
                pay_mngr=AsyncMock(),
                svc_mngr=AsyncMock(),
                usvc_mngr=AsyncMock(),
                promo_mngr=AsyncMock(),
                triggers=AsyncMock(),
            )
        assert exc.value.status_code == 403
        assert "disabled" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_existing_user_require_login_policy_raises_409(self) -> None:
        from api.v1.public import create_guest_purchase
        from schemas.guest import GuestPurchaseCreate

        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(cors_origins_list=[], PUBLIC_URL="http://test.local"))))
        body = GuestPurchaseCreate(email="user@ya.ru", provider="stripe", service_id=1)
        settings = _FakeSettings({
            "shop.guest_checkout.enabled": True,
            "shop.guest_checkout.existing_user_policy": "require_login",
        })

        existing_user = UserModel(id=5, email="user@ya.ru")
        existing_user.role = Role(id=2, key=BaseRole.USER, name="User")

        with patch("models.banned_email_domains.BannedEmailDomainsMngr.is_banned", AsyncMock(return_value=False)):
            with patch("models.user.UserMngr.by_email", AsyncMock(return_value=existing_user)):
                with pytest.raises(HTTPException) as exc:
                    await create_guest_purchase(
                        request=req,
                        body=body,
                        session=AsyncMock(),
                        settings=settings,
                        guest_svc=AsyncMock(),
                        pay_mngr=AsyncMock(),
                        svc_mngr=AsyncMock(),
                        usvc_mngr=AsyncMock(),
                        promo_mngr=AsyncMock(),
                        triggers=AsyncMock(),
                    )
        assert exc.value.status_code == 409
        assert exc.value.detail.get("code") == "EMAIL_REQUIRES_LOGIN"

    @pytest.mark.asyncio
    async def test_existing_user_allow_policy_creates_purchase_with_requires_auth(self) -> None:
        from api.v1.public import create_guest_purchase
        from schemas.guest import GuestPurchaseCreate

        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(cors_origins_list=[], PUBLIC_URL="http://test.local"))))
        body = GuestPurchaseCreate(email="user@ya.ru", provider="stripe", service_id=1)
        settings = _FakeSettings({
            "shop.guest_checkout.enabled": True,
            "shop.guest_checkout.existing_user_policy": "allow_require_auth_to_view",
        })

        existing_user = UserModel(id=5, email="user@ya.ru", login="reg_user")
        existing_user.role = Role(id=2, key=BaseRole.USER, name="User")

        service_mock = SimpleNamespace(id=1, name="VPN", price=Decimal("100.00"), duration=30, price_type="fixed")
        pay_mock = SimpleNamespace(id=77, amount=Decimal("100.00"), currency="USD", payment_url="https://pay.local", status="pending")
        usvc_mock = SimpleNamespace(id=99, private_data={})

        pay_mngr = AsyncMock()
        pay_mngr.create = AsyncMock(return_value=pay_mock)
        pay_mngr.s = AsyncMock()

        svc_mngr = AsyncMock()
        svc_mngr.get_active = AsyncMock(return_value=service_mock)

        usvc_mngr = AsyncMock()
        usvc_mngr.create = AsyncMock(return_value=usvc_mock)

        guest_svc = AsyncMock()
        guest_svc.create_order_view_token = AsyncMock(return_value="secure_order_token_xyz")

        with patch("models.banned_email_domains.BannedEmailDomainsMngr.is_banned", AsyncMock(return_value=False)):
            with patch("models.user.UserMngr.by_email", AsyncMock(return_value=existing_user)):
                res = await create_guest_purchase(
                    request=req,
                    body=body,
                    session=AsyncMock(),
                    settings=settings,
                    guest_svc=guest_svc,
                    pay_mngr=pay_mngr,
                    svc_mngr=svc_mngr,
                    usvc_mngr=usvc_mngr,
                    promo_mngr=AsyncMock(),
                    triggers=AsyncMock(),
                )

        assert res.payment_id == 77
        assert res.user_svc_id == 99
        assert res.order_token == "secure_order_token_xyz"
        assert res.requires_auth is True
        # Проверяем, что токен создавался с флагом requires_auth=True
        guest_svc.create_order_view_token.assert_called_once_with(
            order_id=99, payment_id=77, account_id=5, requires_auth=True
        )


class TestPublicOrderStatusEndpoint:
    @pytest.mark.asyncio
    async def test_get_order_status_masks_keys_when_requires_auth(self) -> None:
        from api.v1.public import get_public_order_status
        from datetime import datetime, timezone

        guest_svc = AsyncMock()
        guest_svc.get_order_token_payload = AsyncMock(return_value={
            "order_id": 12,
            "payment_id": 34,
            "account_id": 7,
            "requires_auth": True,
        })

        usvc_mock = SimpleNamespace(
            id=12,
            service_id=1,
            account_id=7,
            status="active",
            price=Decimal("50.00"),
            created_at=datetime.now(timezone.utc),
            public_data={"product": "SECRET_KEY_12345"},
        )
        payment_mock = SimpleNamespace(status="paid", currency="USD")
        service_mock = SimpleNamespace(name="Steam Key")
        user_mock = UserModel(id=7, email="registered@gmail.com")

        usvc_mngr = AsyncMock()
        usvc_mngr.by_id = AsyncMock(return_value=usvc_mock)

        svc_mngr = AsyncMock()
        svc_mngr.by_id = AsyncMock(return_value=service_mock)

        pay_mngr = SimpleNamespace(s=AsyncMock(get=AsyncMock(return_value=payment_mock)))
        user_mngr = AsyncMock()
        user_mngr.by_id = AsyncMock(return_value=user_mock)

        res = await get_public_order_status(
            order_id=12,
            token="token123",
            guest_svc=guest_svc,
            usvc_mngr=usvc_mngr,
            svc_mngr=svc_mngr,
            pay_mngr=pay_mngr,
            user_mngr=user_mngr,
        )

        assert res.order_id == 12
        assert res.requires_auth is True
        # Ключи и чувствительные данные скрыты!
        assert res.keys is None
        assert res.public_data is None
        assert res.buyer_email_masked == "r***d@gmail.com"

    @pytest.mark.asyncio
    async def test_get_order_status_returns_keys_for_guest(self) -> None:
        from api.v1.public import get_public_order_status
        from datetime import datetime, timezone

        guest_svc = AsyncMock()
        guest_svc.get_order_token_payload = AsyncMock(return_value={
            "order_id": 12,
            "payment_id": 34,
            "account_id": 9,
            "requires_auth": False,
        })

        usvc_mock = SimpleNamespace(
            id=12,
            service_id=1,
            account_id=9,
            status="active",
            price=Decimal("50.00"),
            created_at=datetime.now(timezone.utc),
            public_data={"product": "ACTUAL_GUEST_KEY_XYZ"},
        )
        payment_mock = SimpleNamespace(status="paid", currency="EUR")
        service_mock = SimpleNamespace(name="Game Key")
        user_mock = UserModel(id=9, email="guest@domain.com")

        usvc_mngr = AsyncMock()
        usvc_mngr.by_id = AsyncMock(return_value=usvc_mock)

        svc_mngr = AsyncMock()
        svc_mngr.by_id = AsyncMock(return_value=service_mock)

        pay_mngr = SimpleNamespace(s=AsyncMock(get=AsyncMock(return_value=payment_mock)))
        user_mngr = AsyncMock()
        user_mngr.by_id = AsyncMock(return_value=user_mock)

        res = await get_public_order_status(
            order_id=12,
            token="token123",
            guest_svc=guest_svc,
            usvc_mngr=usvc_mngr,
            svc_mngr=svc_mngr,
            pay_mngr=pay_mngr,
            user_mngr=user_mngr,
        )

        assert res.order_id == 12
        assert res.requires_auth is False
        # Для гостя ключ возвращается!
        assert res.keys == ["ACTUAL_GUEST_KEY_XYZ"]
        assert res.public_data == {"product": "ACTUAL_GUEST_KEY_XYZ"}
        assert res.buyer_email_masked == "g***t@domain.com"

