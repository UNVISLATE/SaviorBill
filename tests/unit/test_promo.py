"""Юнит-тесты промокодов: код-токен + поведение из каталога."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from enums import DiscountType, PromoKind
from models.promo_catalogs import PromoCatalogsModel, PromoCatalogsMngr
from models.promo_codes import PromoCodesModel, PromoCodesMngr
from schemas.promo import PromoCatalogCreate

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


def test_catalog_has_no_parent_id_or_settings():
    """parent_id/settings удалены — каталоги промокодов плоский список."""
    cat_cols = set(PromoCatalogsModel.__table__.columns.keys())
    assert "parent_id" not in cat_cols
    assert "settings" not in cat_cols
    assert "conditions" in cat_cols  # зарезервировано, оставлено


def test_discount_type_required_when_discount():
    with pytest.raises(ValidationError):
        PromoCatalogCreate(name="C", slug="c1", kind=PromoKind.DISCOUNT)


def test_discount_type_forbidden_when_not_discount():
    with pytest.raises(ValidationError):
        PromoCatalogCreate(
            name="C",
            slug="c2",
            kind=PromoKind.SERVICE,
            discount_type=DiscountType.PERCENT,
        )


def test_discount_type_ok_when_discount():
    cat = PromoCatalogCreate(
        name="C",
        slug="c3",
        kind=PromoKind.DISCOUNT,
        discount_type=DiscountType.PERCENT,
    )
    assert cat.discount_type == DiscountType.PERCENT


def test_per_user_rejects_zero_and_negative():
    with pytest.raises(ValidationError):
        PromoCatalogCreate(name="C", slug="c4", per_user=0)
    with pytest.raises(ValidationError):
        PromoCatalogCreate(name="C", slug="c5", per_user=-1)


def test_per_user_none_means_unlimited():
    cat = PromoCatalogCreate(name="C", slug="c6")
    assert cat.per_user is None


def test_validate_kind_discount_manager_accepts_matching():
    PromoCatalogsMngr._validate_kind_discount(PromoKind.DISCOUNT, DiscountType.FIXED)
    PromoCatalogsMngr._validate_kind_discount(PromoKind.BONUS, None)


def test_validate_kind_discount_manager_rejects_mismatch():
    with pytest.raises(HTTPException):
        PromoCatalogsMngr._validate_kind_discount(PromoKind.SERVICE, DiscountType.PERCENT)
    with pytest.raises(HTTPException):
        PromoCatalogsMngr._validate_kind_discount(PromoKind.DISCOUNT, None)

