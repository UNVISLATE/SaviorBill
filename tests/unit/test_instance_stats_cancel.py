import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from api.v1.system.stats import router
from fastapi import FastAPI

pytestmark = pytest.mark.unit


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


@pytest.mark.asyncio
async def test_cancel_user_media_job_endpoint():
    from api.v1.user.media import router as user_media_router
    from dependencies.auth import get_current_acc
    from dependencies.media import get_worker_jobs_mngr
    from dependencies.valkey import get_valkey_client
    from types import SimpleNamespace

    mock_vk = AsyncMock()
    mock_vk.set = AsyncMock(return_value=True)
    mock_vk.hset = AsyncMock(return_value=1)
    mock_vk.publish = AsyncMock(return_value=1)
    mock_vk.hget = AsyncMock(return_value=b"10")

    mock_jobs = AsyncMock()
    active_job = SimpleNamespace(id=1, subject_key="tok_user_1", op="convert")
    mock_jobs.active_for_owner = AsyncMock(return_value=[active_job])
    mock_jobs.apply = AsyncMock()

    user_acc = SimpleNamespace(
        id=10,
        role=SimpleNamespace(key="client", perms={"user": {"media": {"create": True}}}),
    )

    app = FastAPI()
    app.include_router(user_media_router, prefix="/api/v1/user")
    app.dependency_overrides[get_current_acc] = lambda: user_acc
    app.dependency_overrides[get_valkey_client] = lambda: mock_vk
    app.dependency_overrides[get_worker_jobs_mngr] = lambda: mock_jobs

    client = TestClient(app)

    res = client.post("/api/v1/user/media/jobs/tok_user_1/cancel")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    mock_vk.set.assert_called_with("media:cancel:tok_user_1", "1", ex=120)
    mock_jobs.apply.assert_called_once_with(
        kind="media", op="convert", subject_key="tok_user_1", state="cancelled", error="Cancelled by user"
    )
    payload = json.loads(mock_vk.publish.call_args[0][1])
    assert payload["action"] == "cancel"
    assert payload["token"] == "tok_user_1"
