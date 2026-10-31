from __future__ import annotations

import json
from unittest.mock import AsyncMock
import pytest

from services.catalog_cache import (
    get_cached_catalogs,
    get_cached_catalog_ids,
    get_cached_service_entities,
    invalidate_catalog_cache,
    invalidate_catalog_indexes,
    invalidate_service_entity,
    set_cached_catalogs,
    set_cached_catalog_ids,
    set_cached_service_entities,
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
async def test_catalog_ids_cache():
    vk = AsyncMock()
    mock_ids = [1, 2, 3, 5]
    vk.get.return_value = json.dumps(mock_ids)

    cached = await get_cached_catalog_ids(vk, catalog_id=10)
    assert cached == mock_ids
    vk.incr.assert_called_with("cache:stats:hits")

    await set_cached_catalog_ids(vk, catalog_id=10, ids=mock_ids, ttl_sec=3600)
    vk.set.assert_called_once()


@pytest.mark.asyncio
async def test_service_entities_mget_cache():
    vk = AsyncMock()
    mock_svc = {"id": 1, "name": "VPN"}
    # Returns 1 found, 1 missing
    vk.mget.return_value = [json.dumps(mock_svc), None]

    found, missing = await get_cached_service_entities(vk, [1, 2])
    assert 1 in found
    assert found[1] == mock_svc
    assert missing == [2]


@pytest.mark.asyncio
async def test_invalidate_catalog_cache():
    vk = AsyncMock()

    async def mock_scan_iter(match=None, count=None):
        for k in ["cache:catalog:tree", "cache:catalog:ids:all"]:
            yield k

    vk.scan_iter = mock_scan_iter
    vk.delete.return_value = 2

    deleted = await invalidate_catalog_cache(vk)
    assert deleted == 2
    vk.incr.assert_called_with("cache:stats:invalidations")
