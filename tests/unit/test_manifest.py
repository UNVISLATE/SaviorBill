"""Тесты парсинга манифестов и валидации пользовательских форм (sbuiSDK)."""

import pytest
from decimal import Decimal
from fastapi import HTTPException

from schemas.manifest import (
    FieldDefinition,
    FieldOption,
    FieldType,
    ScriptManifest,
)
from services.manifest import (
    ManifestValidationError,
    parse_manifest,
    validate_client_order_form,
)

pytestmark = pytest.mark.unit


def test_manifest_schema_valid():
    """Корректный манифест успешно парсится в модель ScriptManifest."""
    raw = {
        "version": "1.0",
        "name": "Steam Top-Up",
        "slug": "steam-topup",
        "client_order_form": [
            {
                "id": "steam_login",
                "type": "text",
                "label": "Steam Login",
                "required": True,
                "regex": r"^[a-zA-Z0-9_]{3,32}$",
                "regex_error": "Логин должен быть от 3 до 32 символов (a-z, 0-9, _)",
            },
            {
                "id": "region",
                "type": "select",
                "label": "Регион",
                "required": True,
                "default": "CIS",
                "options": [
                    {"value": "CIS", "label": "Россия / СНГ", "price_delta": "0"},
                    {"value": "TR", "label": "Турция", "price_delta": "0"},
                ],
            },
            {
                "id": "extra_pin",
                "type": "number",
                "label": "Пин-код",
                "min": 1000,
                "max": 9999,
                "required": False,
            },
        ],
    }
    manifest = parse_manifest(raw)
    assert manifest.name == "Steam Top-Up"
    assert len(manifest.client_order_form) == 3
    assert manifest.client_order_form[0].regex is not None


def test_manifest_schema_invalid_select_without_options():
    """Поле type=select обязано содержать options."""
    raw = {
        "name": "Bad Select",
        "slug": "bad-select",
        "client_order_form": [
            {"id": "choice", "type": "select", "label": "Выбор"},
        ],
    }
    with pytest.raises(HTTPException) as exc_info:
        parse_manifest(raw)
    assert exc_info.value.status_code == 422


def test_manifest_schema_invalid_min_greater_than_max():
    """min не может быть больше max."""
    raw = {
        "name": "Bad Range",
        "slug": "bad-range",
        "client_order_form": [
            {"id": "num", "type": "number", "label": "Число", "min": 100, "max": 10},
        ],
    }
    with pytest.raises(HTTPException) as exc_info:
        parse_manifest(raw)
    assert exc_info.value.status_code == 422


def test_validate_client_order_form_success_and_anti_pollution():
    """Валидация успешных данных и отсечение лишних полей (Anti-Pollution)."""
    manifest = ScriptManifest(
        name="VPS",
        slug="vps",
        client_order_form=[
            FieldDefinition(
                id="hostname",
                type=FieldType.TEXT,
                label="Hostname",
                required=True,
                min_length=3,
                max_length=64,
            ),
            FieldDefinition(
                id="os",
                type=FieldType.SELECT,
                label="OS",
                required=True,
                options=[
                    FieldOption(value="ubuntu", label="Ubuntu 24.04"),
                    FieldOption(value="debian", label="Debian 12"),
                ],
            ),
            FieldDefinition(
                id="cores",
                type=FieldType.RANGE,
                label="vCPU",
                min=Decimal("1"),
                max=Decimal("16"),
                step=Decimal("1"),
                default=2,
            ),
            FieldDefinition(
                id="backup",
                type=FieldType.TOGGLE,
                label="Backup",
                default=False,
            ),
        ],
    )

    user_input = {
        "hostname": "srv1.saviorvpn.net",
        "os": "ubuntu",
        "cores": 4,
        "backup": "true",
        # Посторонние поля злоумышленника
        "hacked_amount": "0.01",
        "admin_role": True,
        "__proto__": "polluted",
    }

    clean_form = validate_client_order_form(manifest, user_input)

    assert clean_form["hostname"] == "srv1.saviorvpn.net"
    assert clean_form["os"] == "ubuntu"
    assert clean_form["cores"] == 4
    assert clean_form["backup"] is True

    # Проверка Anti-Pollution: посторонние поля строго отсечены
    assert "hacked_amount" not in clean_form
    assert "admin_role" not in clean_form
    assert "__proto__" not in clean_form


def test_validate_client_order_form_missing_required():
    """Отсутствие обязательного поля бросает 400 ManifestValidationError."""
    manifest = ScriptManifest(
        name="Test",
        slug="test",
        client_order_form=[
            FieldDefinition(id="email", type=FieldType.TEXT, label="Email", required=True),
        ],
    )
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_client_order_form(manifest, {})
    assert exc_info.value.status_code == 400
    assert "обязательно" in exc_info.value.detail["message"]


def test_validate_client_order_form_regex_failure():
    """Несовпадение с регулярным выражением вызывает ошибку с кастомным сообщением."""
    manifest = ScriptManifest(
        name="Test",
        slug="test",
        client_order_form=[
            FieldDefinition(
                id="login",
                type=FieldType.TEXT,
                label="Логин",
                regex=r"^[a-z0-9_]{3,16}$",
                regex_error="Только строчные латинские буквы и цифры",
            ),
        ],
    )
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_client_order_form(manifest, {"login": "INVALID LOGIN!!!"})
    assert exc_info.value.status_code == 400
    assert "Только строчные латинские буквы" in exc_info.value.detail["message"]


def test_validate_client_order_form_invalid_select_option():
    """Выбор несуществующей опции селекта отклоняется."""
    manifest = ScriptManifest(
        name="Test",
        slug="test",
        client_order_form=[
            FieldDefinition(
                id="datacenter",
                type=FieldType.SELECT,
                label="ЦОД",
                options=[
                    FieldOption(value="helsinki", label="Helsinki"),
                    FieldOption(value="frankfurt", label="Frankfurt"),
                ],
            ),
        ],
    )
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_client_order_form(manifest, {"datacenter": "moscow_invalid"})
    assert exc_info.value.status_code == 400
    assert "Недопустимое значение" in exc_info.value.detail["message"]


def test_validate_client_order_form_number_bounds_and_step():
    """Проверка min, max и step для числовых полей."""
    manifest = ScriptManifest(
        name="Test",
        slug="test",
        client_order_form=[
            FieldDefinition(
                id="ram",
                type=FieldType.RANGE,
                label="RAM",
                min=Decimal("2"),
                max=Decimal("64"),
                step=Decimal("2"),
            ),
        ],
    )
    # Меньше min
    with pytest.raises(ManifestValidationError):
        validate_client_order_form(manifest, {"ram": 1})

    # Больше max
    with pytest.raises(ManifestValidationError):
        validate_client_order_form(manifest, {"ram": 128})

    # Не кратно шагу (2 + n*2)
    with pytest.raises(ManifestValidationError):
        validate_client_order_form(manifest, {"ram": 5})

    # Валидное число
    res = validate_client_order_form(manifest, {"ram": 8})
    assert res["ram"] == 8


def test_resolve_service_order_with_manifest_integration():
    """Интеграция resolve_service_order с ScriptManifest в pricing_config."""
    from models.service import ServiceModel
    from enums import PriceType
    from services.pricing import resolve_service_order

    manifest_dict = {
        "name": "Cloud VPS",
        "slug": "cloud-vps",
        "client_order_form": [
            {
                "id": "os",
                "type": "select",
                "label": "OS",
                "required": True,
                "options": [
                    {"value": "ubuntu", "label": "Ubuntu 24.04"},
                    {"value": "debian", "label": "Debian 12"},
                ],
            },
            {
                "id": "hostname",
                "type": "text",
                "label": "Server Hostname",
                "required": True,
                "regex": r"^[a-z0-9.-]+$",
            },
        ],
    }

    service = ServiceModel(
        id=77,
        price=Decimal("500.00"),
        currency="RUB",
        price_type=PriceType.FIXED,
        pricing_config={"manifest": manifest_dict},
    )

    # 1. Ошибка: отсутствует обязательное поле hostname
    with pytest.raises(HTTPException) as exc_info:
        resolve_service_order(service, form={"os": "ubuntu"})
    assert exc_info.value.status_code == 400

    # 2. Успешный расчет и изоляция формы в order_config
    resolved = resolve_service_order(
        service,
        form={"os": "ubuntu", "hostname": "node1.cloud", "injected_field": "bad"},
    )
    assert resolved.price == Decimal("500.00")
    assert resolved.order_config["form"] == {
        "os": "ubuntu",
        "hostname": "node1.cloud",
    }
    assert "injected_field" not in resolved.order_config["form"]

