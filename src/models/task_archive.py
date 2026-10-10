"""Долговечный архив выполнения фоновых задач (TaskArchiveModel + TaskArchiveMngr)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class TaskArchiveModel(Base):
    """Постоянная запись об исполнении фоновой задачи (lua, media, billing)."""

    __tablename__ = "task_archive"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    task_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    initiator_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    initiator_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class TaskArchiveMngr:
    """Менеджер долговечного архива фоновых задач в PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def record(
        self,
        task_id: str,
        kind: str,
        operation: str,
        status: str,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        duration_ms: int | None = None,
        initiator_type: str | None = None,
        initiator_id: str | None = None,
        error_message: str | None = None,
        logs: list | None = None,
        meta: dict | None = None,
    ) -> TaskArchiveModel:
        entry = TaskArchiveModel(
            task_id=task_id,
            kind=kind,
            operation=operation,
            status=status,
            started_at=started_at or utc_now(),
            finished_at=finished_at or utc_now(),
            duration_ms=duration_ms,
            initiator_type=initiator_type,
            initiator_id=initiator_id,
            error_message=error_message,
            logs=logs or [],
            meta=meta or {},
        )
        self.s.add(entry)
        await self.s.flush()
        return entry

    async def list_tasks(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        operation: str | None = None,
        initiator_type: str | None = None,
        search: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskArchiveModel], int]:
        stmt = select(TaskArchiveModel)
        count_stmt = select(func.count(TaskArchiveModel.id))

        if kind:
            stmt = stmt.where(TaskArchiveModel.kind == kind)
            count_stmt = count_stmt.where(TaskArchiveModel.kind == kind)
        if status:
            stmt = stmt.where(TaskArchiveModel.status == status)
            count_stmt = count_stmt.where(TaskArchiveModel.status == status)
        if operation:
            stmt = stmt.where(TaskArchiveModel.operation == operation)
            count_stmt = count_stmt.where(TaskArchiveModel.operation == operation)
        if initiator_type:
            stmt = stmt.where(TaskArchiveModel.initiator_type == initiator_type)
            count_stmt = count_stmt.where(
                TaskArchiveModel.initiator_type == initiator_type
            )
        if search:
            stmt = stmt.where(TaskArchiveModel.task_id.ilike(f"%{search}%"))
            count_stmt = count_stmt.where(TaskArchiveModel.task_id.ilike(f"%{search}%"))
        if since:
            stmt = stmt.where(TaskArchiveModel.created_at >= since)
            count_stmt = count_stmt.where(TaskArchiveModel.created_at >= since)
        if until:
            stmt = stmt.where(TaskArchiveModel.created_at <= until)
            count_stmt = count_stmt.where(TaskArchiveModel.created_at <= until)

        total = await self.s.scalar(count_stmt) or 0
        rows = await self.s.scalars(
            stmt.order_by(TaskArchiveModel.id.desc()).offset(offset).limit(limit)
        )
        return list(rows), total

    async def by_id(self, task_id_or_pk: int | str) -> TaskArchiveModel | None:
        if isinstance(task_id_or_pk, int) or (
            isinstance(task_id_or_pk, str) and task_id_or_pk.isdigit()
        ):
            row = await self.s.get(TaskArchiveModel, int(task_id_or_pk))
            if row:
                return row
        return await self.s.scalar(
            select(TaskArchiveModel)
            .where(TaskArchiveModel.task_id == str(task_id_or_pk))
            .order_by(TaskArchiveModel.id.desc())
        )

    async def trim_older_than(self, retention_days: int) -> int:
        from datetime import timedelta

        cutoff = utc_now() - timedelta(days=retention_days)
        res = await self.s.execute(
            delete(TaskArchiveModel).where(TaskArchiveModel.created_at < cutoff)
        )
        return res.rowcount or 0


__all__ = ["TaskArchiveModel", "TaskArchiveMngr"]
