"""Юнит-тесты для Фазы 4: Чистка схемы БД и Task Archive."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from models.task_archive import TaskArchiveMngr, TaskArchiveModel
from schemas.task_archive import (
    TaskArchiveDetail,
    TaskArchiveListItem,
    TaskArchivePage,
)


@pytest.mark.asyncio
async def test_log_model_removed():
    import models

    assert not hasattr(models, "LogModel")
    assert "api_logs" not in models.Base.metadata.tables


@pytest.mark.asyncio
async def test_task_archive_record_and_read():
    mock_session = AsyncMock()
    mock_session.add = Mock()
    mngr = TaskArchiveMngr(mock_session)

    entry = await mngr.record(
        task_id="cid-12345",
        kind="lua",
        operation="run_script",
        status="success",
        duration_ms=45,
        initiator_type="payment",
        initiator_id="99",
        logs=[{"step": 1, "msg": "started"}, {"step": 2, "msg": "done"}],
        meta={"service": "vpn"},
    )

    assert entry.task_id == "cid-12345"
    assert entry.kind == "lua"
    assert entry.status == "success"
    assert entry.duration_ms == 45
    assert len(entry.logs) == 2
    mock_session.add.assert_called_once_with(entry)
    mock_session.flush.assert_awaited_once()


def test_task_archive_schemas_serialization():
    now = datetime.now(timezone.utc)
    model = TaskArchiveModel(
        id=1,
        created_at=now,
        started_at=now,
        finished_at=now + timedelta(seconds=1),
        task_id="task-999",
        kind="media",
        operation="convert_image",
        status="success",
        duration_ms=1050,
        initiator_type="user",
        initiator_id="7",
        error_message=None,
        logs=[{"log": "ok"}],
        meta={"fmt": "webp"},
    )

    list_item = TaskArchiveListItem.model_validate(model)
    assert list_item.id == 1
    assert list_item.task_id == "task-999"
    assert list_item.duration_ms == 1050

    detail = TaskArchiveDetail.model_validate(model)
    assert detail.id == 1
    assert detail.logs == [{"log": "ok"}]
    assert detail.meta == {"fmt": "webp"}

    page = TaskArchivePage(items=[list_item], total=1, page=1, page_size=50)
    assert page.total == 1
    assert len(page.items) == 1


@pytest.mark.asyncio
async def test_get_archived_task_not_found():
    from api.v1.admin.tasks.archive import get_archived_task

    mock_mngr = AsyncMock()
    mock_mngr.by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await get_archived_task("nonexistent", mngr=mock_mngr)
    assert exc.value.status_code == 404
