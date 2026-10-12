"""Юнит-тесты для Фазы 5: Хранилище медиа и пакетная реконсилиация FS/S3."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request

from api.v1.admin.media import get_reconcile_batch_status, preview_orphaned_media
from models.system_media import SystemMediaModel


class _FakeValkey:
    def __init__(self, data: dict | None = None) -> None:
        self.hashes = data or {}

    async def hgetall(self, key: str) -> dict:
        return self.hashes.get(key, {})


@pytest.mark.asyncio
async def test_preview_orphans_non_destructive():
    mock_session = AsyncMock()
    from models.system_media import SystemMediaMngr

    mngr = SystemMediaMngr(mock_session)
    mock_session.scalar.return_value = 2
    mock_session.scalars.return_value = [
        SystemMediaModel(
            id=1,
            token="tok1",
            path="tok1.jpg",
            backend="fs",
            mime="image/jpeg",
            size=100,
            status="ready",
            kind="image",
            variants={},
        ),
        SystemMediaModel(
            id=2,
            token="tok2",
            path="tok2.jpg",
            backend="fs",
            mime="image/jpeg",
            size=200,
            status="ready",
            kind="image",
            variants={},
        ),
    ]

    items, total = await mngr.preview_orphans(grace_sec=3600, limit=10, offset=0)
    assert total == 2
    assert len(items) == 2
    assert items[0].token == "tok1"
    # Метод только делает SELECT, никаких delete или flush
    mock_session.delete.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_batch_status_calculates_summary():
    mock_session = AsyncMock()
    from models.system_media import SystemMediaMngr

    mngr = SystemMediaMngr(mock_session)
    m1 = SystemMediaModel(
        id=10,
        token="tok_healthy",
        path="tok10.jpg",
        backend="fs",
        mime="image/jpeg",
        size=100,
        status="ready",
        kind="image",
        variants={},
    )
    m2 = SystemMediaModel(
        id=11,
        token="tok_missing",
        path="tok11.jpg",
        backend="fs",
        mime="image/jpeg",
        size=200,
        status="ready",
        kind="image",
        variants={},
    )
    mock_session.scalars.return_value = [m1, m2]

    vk = _FakeValkey(
        {
            "media:integrity:tok_healthy": {
                "token": "tok_healthy",
                "state": "healthy",
                "main": "ready",
            },
            "media:integrity:tok_missing": {
                "token": "tok_missing",
                "state": "artifact_missing",
                "main": "missing",
            },
        }
    )

    req = AsyncMock(spec=Request)
    req.app.state.settings = AsyncMock()
    req.app.state.settings.BUS_SIGNING_KEY = ""
    req.app.state.settings.MEDIA_TASK_STREAM = "media:tasks"
    req.app.state.settings.MEDIA_TASK_STREAM_MAXLEN = 1000

    resp = await get_reconcile_batch_status(
        request=req,
        limit=10,
        after_id=0,
        mngr=mngr,
        vk=vk,
    )

    assert resp["total_in_batch"] == 2
    assert resp["summary"]["healthy"] == 1
    assert resp["summary"]["artifact_missing"] == 1
    assert resp["summary"]["artifact_corrupt"] == 0
