"""Юнит-тесты доменных enum-констант и регистрации моделей.

Проверяют корректность сплита ``models`` / ``enums``:
импорт моделей не требует БД, метаданные собираются.
"""

import pytest

import enums
import models

pytestmark = pytest.mark.unit


def test_enum_values_are_strings():
    assert enums.Delivery.KEY == "key"
    assert enums.Delivery.LUA == "lua"
    assert enums.OrderStatus.DELIVERED == "delivered"
    assert enums.PayStatus.PAID == "paid"
    assert enums.PayTarget.SERVICE == "service"
    assert enums.PromoKind.BONUS == "bonus"
    assert enums.ScriptKind.PAYMENT == "payment"


def test_all_tables_registered():
    tables = set(models.Base.metadata.tables)
    # These are actual __tablename__ values (unchanged for migration compat)
    expected = {
        "roles",
        "accounts",
        "oauth_cfg",
        "oauth_conns",
        "lua_scripts",
        "svc_catalogs",
        "services",
        "digi_keys",
        "user_services",
        "pay_providers",
        "payments",
        "promocodes",
        "promo_uses",
        "settings",
        "api_logs",
        "system_media",
        "promo_catalogs",
        "email_templates",
        "triggers",
    }
    assert expected <= tables


def test_basic_columns_in_models():
    # id, created_at/updated_at у обычных моделей (inlined, no mixins).
    cols = models.UserModel.__table__.columns
    assert "id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


def test_apilog_has_trim_classmethod():
    # LogModel должна иметь trim() classmethod для очистки старых записей.
    assert hasattr(models.LogModel, "trim")
    assert callable(getattr(models.LogModel, "trim", None))
    assert models.LogModel.__row_limit__ == 1_000_000
