"""Зависимость менеджера архива задач."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from models.task_archive import TaskArchiveMngr


def get_task_archive_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> TaskArchiveMngr:
    return TaskArchiveMngr(session)


__all__ = ["get_task_archive_mngr"]
