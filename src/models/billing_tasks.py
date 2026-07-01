"""Очередь задач billing-loop (BillingTasksModel) + менеджер (BillingTasksMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    func,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import TaskKind, TaskStatus
from utils.datetime_utils import utc_now


class BillingTasksModel(Base):
    """Отложенная задача биллинга (истечение услуги, перепроверка платежа).

    Планировщик (billing-loop) держит «окно» ближайших задач: при старте — все
    просроченные плюс ближайшие предстоящие, дальше пополняется по событиям.
    ``ref_id`` ссылается на сущность вида ``kind`` (услуга/платёж) без FK, чтобы
    не плодить циклические связи.
    """

    __tablename__ = "billing_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # svc_action | pay_recheck (см. TaskKind).
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    # id сущности (user_services.id или payments.id) — без FK.
    ref_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Действие для svc_action (create/renew/stop/delete/freeze), иначе NULL.
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Момент, когда задачу нужно исполнить.
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=TaskStatus.QUEUED, index=True, nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    payload: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingTasksMngr:
    """Data-access для очереди billing_tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def add(
        self,
        kind: str,
        ref_id: int,
        run_at: datetime,
        *,
        action: str | None = None,
        payload: dict | None = None,
    ) -> BillingTasksModel:
        """Поставить задачу в очередь.

        :arg kind: вид задачи (TaskKind).
        :arg ref_id: id связанной сущности.
        :arg run_at: время исполнения.
        :arg action: действие для svc_action.
        :arg payload: произвольные данные.
        :return: созданная задача.
        """
        task = BillingTasksModel(
            kind=kind,
            ref_id=ref_id,
            action=action,
            run_at=run_at,
            payload=payload or {},
        )
        self.s.add(task)
        await self.s.flush()
        return task

    async def pending_for(self, kind: str, ref_id: int) -> BillingTasksModel | None:
        """Активная (queued) задача для сущности, если есть."""
        return await self.s.scalar(
            select(BillingTasksModel).where(
                BillingTasksModel.kind == kind,
                BillingTasksModel.ref_id == ref_id,
                BillingTasksModel.status == TaskStatus.QUEUED,
            )
        )

    async def due(self, now: datetime, limit: int = 100) -> list[BillingTasksModel]:
        """Готовые к исполнению задачи (queued и run_at <= now)."""
        rows = await self.s.scalars(
            select(BillingTasksModel)
            .where(
                BillingTasksModel.status == TaskStatus.QUEUED,
                BillingTasksModel.run_at <= now,
            )
            .order_by(BillingTasksModel.run_at)
            .limit(limit)
        )
        return list(rows)

    async def next_run_at(self) -> datetime | None:
        """Ближайшее время исполнения среди queued-задач (для сна планировщика)."""
        return await self.s.scalar(
            select(func.min(BillingTasksModel.run_at)).where(
                BillingTasksModel.status == TaskStatus.QUEUED
            )
        )


__all__ = ["BillingTasksModel", "BillingTasksMngr"]
