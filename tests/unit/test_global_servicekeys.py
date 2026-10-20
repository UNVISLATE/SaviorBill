"""Unit тесты для глобального управления ключами /api/v1/admin/service-keys."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from schemas.service_keys import (
    GlobalServiceKeysImportIn,
    ServiceKeysOverviewOut,
    ServiceStockItem,
)
from decimal import Decimal


@pytest.mark.unit
def test_global_service_keys_schemas():
    item = ServiceStockItem(
        service_id=1,
        service_name="VPN Basic",
        service_slug="vpn-basic",
        catalog_id=1,
        catalog_name="VPN",
        price=Decimal("100.00"),
        currency="RUB",
        is_active=True,
        available_keys=10,
        used_keys=5,
        total_keys=15,
        stock_status="ok",
    )
    assert item.stock_status == "ok"
    assert item.available_keys == 10

    overview = ServiceKeysOverviewOut(
        total_available=10,
        total_used=5,
        total_keys=15,
        out_of_stock_count=0,
        low_stock_count=0,
        items=[item],
    )
    assert overview.total_available == 10

    import_in = GlobalServiceKeysImportIn(service_id=1, values=["KEY-1", "KEY-2"])
    assert import_in.service_id == 1
    assert len(import_in.values) == 2
