"""Переиспользуемые миксины для моделей."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class PkMixin:
    """Целочисленный первичный ключ."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TsMixin:
    """Метки времени создания/обновления (UTC, на стороне БД)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LimitMixin:
    """Самоочищающаяся таблица (логи/временные данные).

    Задайте ``__row_limit__`` в модели и периодически вызывайте
    ``trim()`` (например, из планировщика как Event Producer), чтобы
    держать число строк в пределах лимита, удаляя самые старые id.
    """

    __row_limit__: int = 100_000

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    @classmethod
    async def trim(cls, session: AsyncSession, limit: int | None = None) -> int:
        """Удалить строки за пределами лимита (по возрастанию id). Возвращает кол-во удалённых."""
        cap = limit if limit is not None else cls.__row_limit__
        cutoff = await session.scalar(
            select(cls.id).order_by(cls.id.desc()).offset(cap).limit(1)
        )
        if cutoff is None:
            return 0
        res = await session.execute(cls.__table__.delete().where(cls.id <= cutoff))
        return res.rowcount or 0


class JsonDataMixin:
    """Пара JSON-полей: публичные (видит клиент) и приватные (только система).

    Используется сущностями выдачи (``UserSvc``) и платежей (``Payment``), где
    результат интеграции раскладывается на отдаваемую клиенту часть и внутреннюю.
    """

    public_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    private_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


__all__ = ["PkMixin", "TsMixin", "LimitMixin", "JsonDataMixin"]
