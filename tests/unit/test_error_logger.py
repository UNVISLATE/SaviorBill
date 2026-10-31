from __future__ import annotations

import json
from unittest.mock import AsyncMock
import pytest

from services.error_logger import list_request_errors, log_request_error

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_log_request_error():
    vk = AsyncMock()
    err = await log_request_error(
        vk,
        status_code=404,
        path="/api/test",
        method="GET",
        client_ip="1.2.3.4",
        error_detail="Not Found",
        ray_id="sb_ray_abc123",
    )
    assert err["ray_id"] == "sb_ray_abc123"
    assert err["status_code"] == 404
    assert vk.lpush.called


@pytest.mark.asyncio
async def test_list_request_errors_filter():
    vk = AsyncMock()
    items = [
        json.dumps({
            "id": "1",
            "ray_id": "ray1",
            "status_code": 404,
            "path": "/api/missing",
            "client_ip": "1.1.1.1",
            "error_detail": "Missing",
        }),
        json.dumps({
            "id": "2",
            "ray_id": "ray2",
            "status_code": 500,
            "path": "/api/boom",
            "client_ip": "2.2.2.2",
            "error_detail": "Crash",
        }),
    ]
    vk.lrange.return_value = items

    res_all = await list_request_errors(vk)
    assert len(res_all) == 2

    res_404 = await list_request_errors(vk, status_code=404)
    assert len(res_404) == 1
    assert res_404[0]["status_code"] == 404

    res_search = await list_request_errors(vk, search="boom")
    assert len(res_search) == 1
    assert res_search[0]["path"] == "/api/boom"
