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
        trace_id="0123456789abcdef0123456789abcdef",
        query_params="foo=bar",
        duration_ms=15.4,
        user_agent="Mozilla/5.0",
    )
    assert err["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert err["status_code"] == 404
    assert err["duration_ms"] == 15.4
    assert err["query_params"] == "foo=bar"
    assert vk.lpush.called


@pytest.mark.asyncio
async def test_list_request_errors_filter():
    vk = AsyncMock()
    items = [
        json.dumps({
            "id": "1",
            "trace_id": "trace1",
            "status_code": 404,
            "path": "/api/missing",
            "client_ip": "1.1.1.1",
            "error_detail": "Missing",
        }),
        json.dumps({
            "id": "2",
            "trace_id": "trace2",
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


def test_extract_user_telemetry_fallback():
    import jwt
    from starlette.requests import Request
    from middleware.request_tracker import _extract_user_telemetry

    # 1. State snapshot
    scope = {"type": "http", "headers": [], "state": {}}
    req = Request(scope)
    req.state.user_snapshot = (42, "admin_user", "owner")
    assert _extract_user_telemetry(req) == (42, "admin_user", "owner")

    # 2. sb_refresh cookie fallback when expired access token or 401
    refresh_token = jwt.encode(
        {"sub": "99", "login": "test_owner", "role": "owner"},
        "dummy",
        algorithm="HS256",
    )
    cookie_hdr = (b"cookie", f"sb_refresh={refresh_token}".encode())
    req_cookie = Request({"type": "http", "headers": [cookie_hdr], "state": {}})
    uid, login, role = _extract_user_telemetry(req_cookie)
    assert uid == 99
    assert login == "test_owner"
    assert role == "owner"

