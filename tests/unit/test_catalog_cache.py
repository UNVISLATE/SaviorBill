from __future__ import annotations

import json
from unittest.mock import AsyncMock
import pytest

from services.catalog_cache import (
    flush_cache_data,
    get_cached_catalogs,
    get_cached_services,
    invalidate_catalog_cache,
    set_cached_catalogs,
    set_cached_services,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_catalogs_cache_set_and_get():
    vk = AsyncMock()
    mock_data = [{"id": 1, "name": "Games"}]
    vk.get.return_value = json.dumps(mock_data)

    cached = await get_cached_catalogs(vk)
    assert cached == mock_data
    vk.incr.assert_called_with("cache:stats:hits")

    await set_cached_catalogs(vk, mock_data, ttl_sec=120)
    vk.set.assert_called_once()


@pytest.mark.asyncio
async def test_services_cache_miss():
    vk = AsyncMock()
    vk.get.return_value = None

    cached = await get_cached_services(vk, catalog_id=1, limit=10, offset=0)
    assert cached is None
    vk.incr.assert_called_with("cache:stats:misses")


@pytest.mark.asyncio
async def test_invalidate_catalog_cache():
    vk = AsyncMock()

    async def mock_scan_iter(match=None, count=None):
        for k in ["cache:catalog:tree", "cache:catalog:services:1:10:0"]:
            yield k

    vk.scan_iter = mock_scan_iter
    vk.delete.return_value = 2

    deleted = await invalidate_catalog_cache(vk)
    assert deleted == 2
    vk.incr.assert_called_with("cache:stats:invalidations")
