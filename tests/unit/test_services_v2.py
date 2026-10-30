"""Unit tests for Services 2.0 (Service Engine 2.0).

Tests all 4 pricing modes: fixed, custom, tiered, configurable,
Pydantic validation, Zero-Trust price resolution, and Lua context assembly.
"""

from __future__ import annotations

from decimal import Decimal
import pytest
from fastapi import HTTPException

from enums import Delivery, PriceType, PayTarget
from models.service import ServiceModel
from models.user_services import UserServicesModel
from models.user import UserModel
from schemas.service import (
    ServiceCreate,
    ServicePatch,
    CustomPricingConfig,
    TieredPricingConfig,
    ConfigurablePricingConfig,
)
from schemas.orders import OrderCreate, Order
from schemas.payments import PaymentCreate
from services.pricing import (
    deep_merge,
    set_dot_path,
    unflatten_dot_dict,
    resolve_service_order,
)
from lua.context import build_service_ctx


def test_deep_merge_and_dot_path():
    base = {"a": 1, "sub": {"x": 10, "y": 20}}
    override = {"b": 2, "sub": {"y": 99, "z": 30}}
    merged = deep_merge(base, override)
    assert merged == {"a": 1, "b": 2, "sub": {"x": 10, "y": 99, "z": 30}}
    assert base["sub"]["y"] == 20  # original unchanged

    target = {}
    set_dot_path(target, "server.network.ipv4", "192.168.1.1")
    assert target == {"server": {"network": {"ipv4": "192.168.1.1"}}}

    flat = {"steam.login": "player1", "server.ip": "1.2.3.4", "simple": 123}
    unflat = unflatten_dot_dict(flat)
    assert unflat == {
        "steam": {"login": "player1"},
        "server": {"ip": "1.2.3.4"},
        "simple": 123,
    }


def test_fixed_pricing_backward_compatibility():
    svc = ServiceModel(
        id=1,
        slug="vpn-fixed",
        name="VPN 30 Days",
        price=Decimal("150.00"),
        currency="RUB",
        price_type=PriceType.FIXED,
        pricing_config={},
        duration=2592000,
        settings={"protocol": "wireguard", "port": 51820},
    )

    resolved = resolve_service_order(svc)
    assert resolved.price == Decimal("150.00")
    assert resolved.duration == 2592000
    assert resolved.effective_settings == {"protocol": "wireguard", "port": 51820}
    assert resolved.order_config == {}


def test_custom_pricing_validation_and_resolution():
    svc = ServiceModel(
        id=2,
        slug="steam-topup",
        name="Steam Refill",
        price=Decimal("100.00"),  # "от 100 ₽"
        currency="RUB",
        price_type=PriceType.CUSTOM,
        pricing_config={
            "min": "100.00",
            "max": "5000.00",
            "step": "50.00",
            "form": [
                {
                    "key": "steam_login",
                    "label": "Steam Login",
                    "required": True,
                    "regex": r"^[a-zA-Z0-9_]{3,32}$",
                    "regex_error": "Steam login must be 3-32 alphanumeric characters",
                },
                {
                    "key": "promo_note",
                    "label": "Note",
                    "required": False,
                },
            ],
        },
        duration=None,
        settings={"vendor": "steam_direct"},
    )

    # 1. Missing custom_amount
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, custom_amount=None)
    assert exc.value.status_code == 400
    assert "custom_amount is required" in exc.value.detail

    # 2. Out of bounds (below min)
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, custom_amount=Decimal("50.00"))
    assert exc.value.status_code == 400
    assert "must be between" in exc.value.detail

    # 3. Out of bounds (above max)
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, custom_amount=Decimal("5050.00"))
    assert exc.value.status_code == 400
    assert "must be between" in exc.value.detail

    # 4. Invalid step (not multiple of 50 starting from 100)
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, custom_amount=Decimal("125.00"))
    assert exc.value.status_code == 400
    assert "multiple of 50" in exc.value.detail

    # 5. Missing required form field
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(
            svc, custom_amount=Decimal("250.00"), form={"promo_note": "hello"}
        )
    assert exc.value.status_code == 400
    assert "steam_login" in exc.value.detail

    # 6. Regex failure
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(
            svc,
            custom_amount=Decimal("250.00"),
            form={"steam_login": "a!"},
        )
    assert exc.value.status_code == 400
    assert "3-32 alphanumeric" in exc.value.detail

    # 7. Valid custom order
    resolved = resolve_service_order(
        svc,
        custom_amount=Decimal("350.00"),
        form={"steam_login": "alex_gamer", "promo_note": "bonus please"},
    )
    assert resolved.price == Decimal("350.00")
    assert resolved.duration is None
    assert resolved.effective_settings == {"vendor": "steam_direct"}
    assert resolved.order_config == {
        "amount": "350.00",
        "form": {"steam_login": "alex_gamer", "promo_note": "bonus please"},
    }


def test_tiered_pricing_validation_and_resolution():
    svc = ServiceModel(
        id=3,
        slug="vpn-tiers",
        name="VPN Multi-Period",
        price=Decimal("199.00"),
        currency="RUB",
        price_type=PriceType.TIERED,
        pricing_config={
            "tiers": [
                {
                    "code": "1m",
                    "title": "1 Месяц",
                    "subtiers": [
                        {
                            "code": "1m_basic",
                            "title": "1 Месяц (Basic)",
                            "price": "199.00",
                            "duration_days": 30,
                            "settings_override": {"speed_limit_mbps": 50, "devices": 2},
                        },
                        {
                            "code": "1m_ultra",
                            "title": "1 Месяц (Ultra)",
                            "price": "399.00",
                            "duration_days": 30,
                            "settings_override": {"speed_limit_mbps": 1000, "devices": 10},
                        },
                    ],
                },
                {
                    "code": "1y",
                    "title": "1 Год",
                    "subtiers": [
                        {
                            "code": "1y_ultra",
                            "title": "1 Год (Ultra VIP)",
                            "price": "2990.00",
                            "duration_days": 365,
                            "settings_override": {
                                "speed_limit_mbps": 1000,
                                "devices": 25,
                                "vip_support": True,
                            },
                        }
                    ],
                },
            ]
        },
        duration=None,
        settings={"protocol": "vless", "devices": 1, "speed_limit_mbps": 20},
    )

    # 1. Missing tier_code
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, tier_code=None)
    assert exc.value.status_code == 400
    assert "tier_code is required" in exc.value.detail

    # 2. Unknown tier_code
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, tier_code="nonexistent")
    assert exc.value.status_code == 400
    assert "not found" in exc.value.detail

    # 3. Valid tier selection (1m_ultra)
    resolved = resolve_service_order(svc, tier_code="1m_ultra")
    assert resolved.price == Decimal("399.00")
    assert resolved.duration == 30 * 86400
    # Check deep merge: protocol preserved from base, devices and speed overridden
    assert resolved.effective_settings == {
        "protocol": "vless",
        "devices": 10,
        "speed_limit_mbps": 1000,
    }
    assert resolved.order_config["group"]["code"] == "1m"
    assert resolved.order_config["tier"]["code"] == "1m_ultra"
    assert resolved.order_config["tier"]["duration_days"] == 30


def test_configurable_pricing_validation_and_resolution():
    svc = ServiceModel(
        id=4,
        slug="vds-config",
        name="Cloud VDS",
        price=Decimal("200.00"),  # Base price
        currency="RUB",
        price_type=PriceType.CONFIGURABLE,
        pricing_config={
            "components": [
                {
                    "code": "vcpu",
                    "name": "Процессор",
                    "type": "slider",
                    "unit": "vCPU",
                    "unit_price": "100.00",
                    "min": "1",
                    "max": "16",
                    "step": "1",
                    "default": "1",
                    "path": "resources.vcpu",
                },
                {
                    "code": "ram",
                    "name": "Память",
                    "type": "slider",
                    "unit": "GB",
                    "unit_price": "50.00",
                    "min": "2",
                    "max": "64",
                    "step": "2",
                    "default": "2",
                    "path": "resources.ram_gb",
                },
                {
                    "code": "os",
                    "name": "ОС",
                    "type": "select",
                    "path": "system.os",
                    "default": "ubuntu_22",
                    "options": [
                        {"value": "ubuntu_22", "label": "Ubuntu 22.04", "price_delta": "0.00"},
                        {"value": "debian_12", "label": "Debian 12", "price_delta": "0.00"},
                        {"value": "win_server", "label": "Windows Server 2022", "price_delta": "350.00"},
                    ],
                },
            ]
        },
        duration=2592000,
        settings={"hypervisor": "kvm", "network": {"speed": 100}},
    )

    # 1. Invalid select option
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, components={"os": "arch_linux"})
    assert exc.value.status_code == 400
    assert "invalid option" in exc.value.detail

    # 2. Exceeds max
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, components={"vcpu": 32})
    assert exc.value.status_code == 400
    assert "exceeds max" in exc.value.detail

    # 3. Invalid step
    with pytest.raises(HTTPException) as exc:
        resolve_service_order(svc, components={"ram": 5})
    assert exc.value.status_code == 400
    assert "must be a multiple of 2" in exc.value.detail

    # 4. Valid configurable order
    # Base: 200 + (4 vcpu * 100 = 400) + (8 GB * 50 = 400) + (win_server = 350) = 1350
    resolved = resolve_service_order(
        svc,
        components={"vcpu": 4, "ram": 8, "os": "win_server"},
    )
    assert resolved.price == Decimal("1350.00")
    assert resolved.duration == 2592000
    assert resolved.effective_settings["hypervisor"] == "kvm"
    assert resolved.effective_settings["resources"]["vcpu"] == 4
    assert resolved.effective_settings["resources"]["ram_gb"] == 8
    assert resolved.effective_settings["system"]["os"] == "win_server"
    assert resolved.order_config["components"]["vcpu"]["value"] == 4
    assert resolved.order_config["components"]["os"]["value"] == "win_server"


def test_lua_context_order_and_form_isolation():
    acc = UserModel(
        id=42,
        login="gamemaster",
        email="gm@example.com",
        balance=Decimal("1000.00"),
        bonus_balance=Decimal("50.00"),
    )
    svc = ServiceModel(
        id=10,
        slug="steam-auto",
        name="Steam Auto Refill",
        price=Decimal("100.00"),
        currency="RUB",
        price_type=PriceType.CUSTOM,
        pricing_config={},
        delivery=Delivery.LUA,
        duration=None,
        settings={"api_endpoint": "https://api.steamrefill.test/v1"},
    )
    usvc = UserServicesModel(
        id=777,
        account_id=acc.id,
        service_id=svc.id,
        status="active",
        price=Decimal("750.00"),
        discount=Decimal("0.00"),
        duration=None,
        actions=[],
        public_data={},
        private_data={},
        order_config={
            "amount": "750.00",
            "form": {
                "steam.login": "vitaliy_best",
                "target.country": "RU",
            },
            "settings": {"api_endpoint": "https://api.steamrefill.test/v1"},
        },
    )

    ctx = build_service_ctx("create", acc, usvc, svc)
    assert ctx["action"] == "create"
    assert ctx["service"]["settings"] == {"api_endpoint": "https://api.steamrefill.test/v1"}
    assert ctx["order"]["amount"] == "750.00"
    assert ctx["order"]["currency"] == "RUB"
    # Verify strict unflattening into ctx.order.form.*
    assert ctx["order"]["form"] == {
        "steam": {"login": "vitaliy_best"},
        "target": {"country": "RU"},
    }


def test_pydantic_schemas_services_v2():
    # 1. Custom bounds validation
    with pytest.raises(ValueError):
        CustomPricingConfig(min=Decimal("500"), max=Decimal("100"))

    # 2. ServiceCreate with custom and delivery constraints
    with pytest.raises(ValueError, match="delivery 'key' is only supported for price_type='fixed'"):
        ServiceCreate(
            slug="new-custom",
            name="New Custom",
            price_type=PriceType.CUSTOM,
            pricing_config={"min": "50", "max": "500", "step": "10"},
            delivery="key",
        )

    create_dto = ServiceCreate(
        slug="new-custom",
        name="New Custom",
        price_type=PriceType.CUSTOM,
        pricing_config={"min": "50", "max": "500", "step": "10"},
        delivery="lua",
    )
    assert create_dto.price_type == PriceType.CUSTOM
    assert create_dto.pricing_config["min"] == "50"

    # 3. ServicePatch invalid price_type
    with pytest.raises(ValueError):
        ServicePatch(price_type="quantum")

    # 4. PaymentCreate validation
    # amount must not be supplied for target=service
    with pytest.raises(ValueError):
        PaymentCreate(
            provider="test",
            target=PayTarget.SERVICE,
            service_id=1,
            amount=Decimal("100"),
        )
    # custom_amount must not be supplied for target=balance
    with pytest.raises(ValueError):
        PaymentCreate(
            provider="test",
            target=PayTarget.BALANCE,
            amount=Decimal("100"),
            custom_amount=Decimal("100"),
        )
    # Valid service payment create
    p = PaymentCreate(
        provider="test",
        target=PayTarget.SERVICE,
        service_id=1,
        custom_amount=Decimal("250.00"),
        tier_code="1m_pro",
    )
    assert p.target == PayTarget.SERVICE
    assert p.custom_amount == Decimal("250.00")
    assert p.tier_code == "1m_pro"
