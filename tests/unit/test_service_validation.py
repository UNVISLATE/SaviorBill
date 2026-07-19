"""Юнит-тесты валидации схем услуги (Phase 9): delivery-реестр, а не enum."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lifecycle.fulfillment import known_delivery_kinds
from schemas.service import ServiceCreate, ServicePatch

pytestmark = pytest.mark.unit


def test_known_delivery_kinds_contains_key_and_lua():
    kinds = known_delivery_kinds()
    assert "key" in kinds
    assert "lua" in kinds


def test_service_create_accepts_known_delivery():
    sc = ServiceCreate(slug="abc", name="Товар", delivery="key")
    assert sc.delivery == "key"
    sc2 = ServiceCreate(slug="abd", name="Товар2", delivery="lua")
    assert sc2.delivery == "lua"


def test_service_create_rejects_unknown_delivery():
    with pytest.raises(ValidationError):
        ServiceCreate(slug="abc", name="Товар", delivery="unknown-kind")


def test_service_patch_allows_none_delivery():
    sp = ServicePatch()
    assert sp.delivery is None


def test_service_patch_rejects_unknown_delivery():
    with pytest.raises(ValidationError):
        ServicePatch(delivery="unknown-kind")


def test_service_patch_accepts_known_delivery():
    sp = ServicePatch(delivery="lua")
    assert sp.delivery == "lua"
