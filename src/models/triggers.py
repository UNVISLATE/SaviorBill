"""Триггеры (TriggerModel) + менеджер (TriggerMngr)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class TriggerModel(Base):
    """Привязка «событие → действие» с необязательным условием.

    ``event``  — доменное событие (см. integrations.triggers.events.TriggerEvent).
    ``action`` — ключ действия (``email``, ``lua`` …; см. integrations.triggers).
    ``config`` — параметры действия (для email: ``template_id``/``to_field``;
    для lua: ``script_id``). ``cond`` — пары ``{path: value}``, все должны совпасть.
    """

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cond: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TriggerMngr:
    """CRUD триггеров."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_all(self) -> list[TriggerModel]:
        """Все триггеры по порядку id.

        :return: список триггеров.
        """
        rows = await self.s.scalars(select(TriggerModel).order_by(TriggerModel.id))
        return list(rows)

    async def by_event(self, event: str) -> list[TriggerModel]:
        """Активные триггеры заданного события.

        :arg event: имя доменного события.
        :return: список активных триггеров.
        """
        rows = await self.s.scalars(
            select(TriggerModel).where(
                TriggerModel.event == event,
                TriggerModel.is_active.is_(True),
            )
        )
        return list(rows)

    async def by_id(self, trig_id: int) -> TriggerModel | None:
        """Найти триггер по id.

        :arg trig_id: идентификатор триггера.
        :return: триггер или ``None``.
        """
        return await self.s.get(TriggerModel, trig_id)

    async def create(self, data: dict) -> TriggerModel:
        """Создать триггер.

        :arg data: поля триггера (event, action, config, cond, ...).
        :return: созданный триггер.
        """
        row = TriggerModel(**data)
        self.s.add(row)
        await self.s.flush()
        return row

    async def patch(self, trig_id: int, data: dict) -> TriggerModel:
        """Обновить переданные поля триггера.

        :arg trig_id: идентификатор триггера.
        :arg data: изменяемые поля.
        :return: обновлённый триггер.
        """
        row = await self.by_id(trig_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "триггер не найден")
        for field, val in data.items():
            setattr(row, field, val)
        await self.s.flush()
        return row

    async def delete(self, trig_id: int) -> None:
        """Удалить триггер.

        :arg trig_id: идентификатор триггера.
        """
        row = await self.by_id(trig_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "триггер не найден")
        await self.s.delete(row)
        await self.s.flush()


__all__ = ["TriggerModel", "TriggerMngr"]
