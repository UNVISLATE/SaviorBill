import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from api.v1.system.stats import router
from fastapi import FastAPI


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return app


@pytest.mark.asyncio
async def test_cancel_media_process_endpoint():
    from dependencies.auth import get_current_acc
    from dependencies.valkey import get_valkey_client
    from types import SimpleNamespace

    mock_vk = AsyncMock()
    mock_vk.set = AsyncMock(return_value=True)
    mock_vk.hset = AsyncMock(return_value=1)
    mock_vk.publish = AsyncMock(return_value=1)

    admin_acc = SimpleNamespace(
        id=1,
        role=SimpleNamespace(key="owner", perms={"*": True}),
    )

    app = FastAPI()
    app.state.db_sessionmaker = MagicMock()
    app.include_router(router, prefix="/api/v1/system")
    app.dependency_overrides[get_current_acc] = lambda: admin_acc
    app.dependency_overrides[get_valkey_client] = lambda: mock_vk

    client = TestClient(app)

    # 1. No token and no pid -> 400
    res = client.post("/api/v1/system/instances/media/cancel", json={})
    assert res.status_code == 400

    # 2. Token cancellation
    res = client.post("/api/v1/system/instances/media/cancel", json={"token": "tok123"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    mock_vk.set.assert_called_with("media:cancel:tok123", "1", ex=120)
    mock_vk.publish.assert_called_once()
    payload = json.loads(mock_vk.publish.call_args[0][1])
    assert payload["action"] == "cancel"
    assert payload["token"] == "tok123"

    # 3. PID cancellation
    mock_vk.publish.reset_mock()
    res = client.post("/api/v1/system/instances/media/cancel", json={"pid": 4321})
    assert res.status_code == 200
    payload = json.loads(mock_vk.publish.call_args[0][1])
    assert payload["action"] == "cancel"
    assert payload["pid"] == 4321
