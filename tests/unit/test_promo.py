"""Юнит-тесты промокодов: код-токен + поведение из каталога."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from enums import DiscountType, PromoKind
from models.promo_catalogs import PromoCatalogsModel
from models.promo_codes import PromoCodesModel, PromoCodesMngr

pytestmark = pytest.mark.unit


def _mngr() -> PromoCodesMngr:
    return PromoCodesMngr(session=None)


def test_discount_percent():
    catalog = SimpleNamespace(
        kind=PromoKind.DISCOUNT, discount_type=DiscountType.PERCENT, value=Decimal("10")
    )
    service = SimpleNamespace(price=Decimal("200"))
    assert _mngr().discount_for(catalog, service) == Decimal("20.00")


def test_discount_fixed_caps_at_price():
    catalog = SimpleNamespace(
        kind=PromoKind.DISCOUNT, discount_type=DiscountType.FIXED, value=Decimal("999")
    )
    service = SimpleNamespace(price=Decimal("150"))
    assert _mngr().discount_for(catalog, service) == Decimal("150")


def test_discount_rejects_non_discount_kind():
    catalog = SimpleNamespace(
        kind=PromoKind.BONUS, discount_type=DiscountType.PERCENT, value=Decimal("10")
    )
    service = SimpleNamespace(price=Decimal("100"))
    with pytest.raises(HTTPException):
        _mngr().discount_for(catalog, service)


def test_behavior_lives_on_catalog_not_code():
    code_cols = set(PromoCodesModel.__table__.columns.keys())
    cat_cols = set(PromoCatalogsModel.__table__.columns.keys())

    # Каталог обязателен у кода.
    assert "catalog_id" in code_cols
    assert PromoCodesModel.__table__.columns["catalog_id"].nullable is False

    # Поведение — только в каталоге, не в коде.
    for field in ("kind", "value", "discount_type", "service_id", "per_user"):
        assert field in cat_cols
        assert field not in code_cols
