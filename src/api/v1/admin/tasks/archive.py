"""Админ: долговечный архив фоновых задач в PostgreSQL (/api/v1/admin/tasks/archive)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies.rbac import require_perm
from dependencies.task_archive import get_task_archive_mngr
from models.task_archive import TaskArchiveMngr
from schemas.task_archive import (
    TaskArchiveDetail,
    TaskArchiveListItem,
    TaskArchivePage,
)

router = APIRouter()


@router.get(
    "",
    response_model=TaskArchivePage,
    dependencies=[Depends(require_perm("system.tasks.summary.read"))],
    summary="List archived tasks",
    description="Постраничный список долговечного архива задач с фильтрацией по типу, статусу и дате.",
)
async def list_archived_tasks(
    kind: str | None = Query(default=None, description="lua, media, billing"),
    status_filter: str | None = Query(
        default=None, alias="status", description="success, failed, timeout, running"
    ),
    operation: str | None = Query(default=None),
    initiator_type: str | None = Query(default=None),
    search: str | None = Query(default=None, description="Поиск по task_id"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    mngr: TaskArchiveMngr = Depends(get_task_archive_mngr),
) -> TaskArchivePage:
    offset = (page - 1) * page_size
    items, total = await mngr.list_tasks(
        kind=kind,
        status=status_filter,
        operation=operation,
        initiator_type=initiator_type,
        search=search,
        since=since,
        until=until,
        limit=page_size,
        offset=offset,
    )
    return TaskArchivePage(
        items=[TaskArchiveListItem.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{task_id}",
    response_model=TaskArchiveDetail,
    dependencies=[Depends(require_perm("system.tasks.tail.read"))],
    summary="Get archived task details",
    description="Детальная информация о выполненной задаче, включая логи исполнения и ошибки.",
)
async def get_archived_task(
    task_id: str,
    mngr: TaskArchiveMngr = Depends(get_task_archive_mngr),
) -> TaskArchiveDetail:
    task = await mngr.by_id(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "archived task not found")
    return TaskArchiveDetail.model_validate(task)


__all__ = ["router"]
