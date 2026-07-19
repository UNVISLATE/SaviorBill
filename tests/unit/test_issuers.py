"""Юнит-тесты реестра способов выдачи услуг (issuers)."""

from __future__ import annotations

import pytest

from enums import Delivery
from lifecycle.delivery import KeyService, get_issuer
from lua.integrations.delivery import LuaService

pytestmark = pytest.mark.unit


def test_key_delivery_maps_to_key_service():
    iss = get_issuer(Delivery.KEY, session=None)
    assert isinstance(iss, KeyService)


def test_lua_delivery_maps_to_lua_service():
    iss = get_issuer(Delivery.LUA, session=None, bus="bus")
    assert isinstance(iss, LuaService)
    assert iss.bus == "bus"


def test_unknown_delivery_defaults_to_lua():
    iss = get_issuer("???", session=None)
    assert isinstance(iss, LuaService)
