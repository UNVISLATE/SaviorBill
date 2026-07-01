"""Лог обращений к API (LogModel) — самоочищающаяся таблица."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, BigInteger, DateTime, Integer, JSON, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class LogModel(Base):
    """Запись лога API. Старые строки подрезаются ``LogModel.trim()``."""

    __tablename__ = "api_logs"
    # Потолок по умолчанию; вызывающий передаёт limit из cfg.LOG_ROW_LIMIT.
    __row_limit__: int = 1_000_000

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

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


__all__ = ["LogModel"]
