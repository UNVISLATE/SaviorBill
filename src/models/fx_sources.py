"""Источники курсов валют (FxSourcesModel) + менеджер."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    func,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class FxSourcesModel(Base):
    """Источник курсов валют в цепочке приоритетов."""

    __tablename__ = "fx_sources"

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

    # Тип источника: "provider" | "lua" | "manual"
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    # Для type == "provider":
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Зашифрованный через SecBox API-ключ:
    api_key_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Для type == "lua":
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    lua_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Для type == "manual": фиксированные курсы {CURRENCY: RATE}
    rates: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )

    # Последнее успешное состояние курсов в БД (для Fail-Open):
    last_rates: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Ошибки последнего обновления:
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FxSourcesMngr:
    """Управление источниками курсов в БД."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_all(self) -> list[FxSourcesModel]:
        rows = await self.s.scalars(
            select(FxSourcesModel).order_by(FxSourcesModel.priority.asc(), FxSourcesModel.id.asc())
        )
        return list(rows)

    async def list_enabled(self) -> list[FxSourcesModel]:
        rows = await self.s.scalars(
            select(FxSourcesModel)
            .where(FxSourcesModel.enabled.is_(True))
            .order_by(FxSourcesModel.priority.asc(), FxSourcesModel.id.asc())
        )
        return list(rows)

    async def by_id(self, source_id: int) -> FxSourcesModel | None:
        return await self.s.get(FxSourcesModel, source_id)


__all__ = ["FxSourcesModel", "FxSourcesMngr"]
