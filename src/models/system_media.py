"""Системные медиа-файлы (SystemMediaModel) + менеджер (SystemMediaMngr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class SystemMediaModel(Base):
    """Медиа-файл системы (изображение, иконка, аватар и т.п.)."""

    __tablename__ = "system_media"

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

    kind: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # image/video/icon/avatar
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # fs path or s3 key
    backend: Mapped[str] = mapped_column(String(8), default="fs", nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )  # uploader account id
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SystemMediaMngr:
    """CRUD для системных медиа-файлов."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, media_id: int) -> SystemMediaModel | None:
        return await self.s.get(SystemMediaModel, media_id)

    async def list_all(
        self, limit: int = 100, offset: int = 0
    ) -> list[SystemMediaModel]:
        rows = await self.s.scalars(
            select(SystemMediaModel)
            .order_by(SystemMediaModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def list_by_owner(self, owner_id: int) -> list[SystemMediaModel]:
        rows = await self.s.scalars(
            select(SystemMediaModel)
            .where(SystemMediaModel.owner_id == owner_id)
            .order_by(SystemMediaModel.id.desc())
        )
        return list(rows)

    async def create(
        self,
        kind: str,
        path: str,
        *,
        backend: str = "fs",
        mime: str | None = None,
        size: int | None = None,
        owner_id: int | None = None,
        meta: dict | None = None,
    ) -> SystemMediaModel:
        media = SystemMediaModel(
            kind=kind,
            path=path,
            backend=backend,
            mime=mime,
            size=size,
            owner_id=owner_id,
            meta=meta or {},
        )
        self.s.add(media)
        await self.s.flush()
        return media


__all__ = ["SystemMediaModel", "SystemMediaMngr"]
