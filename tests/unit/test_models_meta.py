"""Юнит-тесты доменных enum-констант и регистрации моделей.

Проверяют корректность сплита ``models`` / ``enums`` / ``orm.mixins``:
импорт моделей не требует БД, метаданные собираются, миксины применяются.
"""

import pytest

import enums
import models
from orm.mixins import LimitMixin, PkMixin, TsMixin

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
    expected = {
        "roles", "accounts", "oauth_cfg", "oauth_conns", "lua_scripts",
        "svc_catalogs", "services", "digi_keys", "user_services",
        "pay_providers", "payments", "promocodes", "promo_uses",
        "settings", "api_logs",
    }
    assert expected <= tables


def test_mixins_applied_to_models():
    # PkMixin -> id, TsMixin -> created_at/updated_at у обычных моделей.
    cols = models.Account.__table__.columns
    assert "id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


def test_limit_mixin_used_by_apilog():
    assert issubclass(models.ApiLog, LimitMixin)
    assert models.ApiLog.__row_limit__ == 1_000_000


def test_mixin_classes_importable_from_orm():
    assert PkMixin and TsMixin and LimitMixin
