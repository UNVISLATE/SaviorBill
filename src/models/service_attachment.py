"""Вложения товара (ServiceAttachmentModel) + менеджер (ServiceAttachmentMngr).

Товар (услуга) может иметь несколько медиа (фото/видео) вместо одиночной картинки.
Каждое вложение — ссылка на запись :class:`SystemMediaModel` + текстовый тег,
который задаёт фронтенд при добавлении (до 16 символов), и порядок сортировки.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import (
    func,
    DateTime,
    ForeignKey,
    Integer,
    String,
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base
from utils.datetime_utils import utc_now


class ServiceAttachmentModel(Base):
    """Вложение товара: медиа + тег."""

    __tablename__ = "service_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("system_media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Тег, задаётся фронтендом при добавлении (напр. "cover", "screenshot").
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    media: Mapped["SystemMediaModel"] = relationship(  # noqa: F821
        "SystemMediaModel", lazy="selectin"
    )


class ServiceAttachmentMngr:
    """CRUD вложений товара."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, att_id: int) -> ServiceAttachmentModel | None:
        return await self.s.get(ServiceAttachmentModel, att_id)

    async def list_by_service(self, service_id: int) -> list[ServiceAttachmentModel]:
        rows = await self.s.scalars(
            select(ServiceAttachmentModel)
            .where(ServiceAttachmentModel.service_id == service_id)
            .order_by(ServiceAttachmentModel.position, ServiceAttachmentModel.id)
        )
        return list(rows)

    async def add(
        self,
        service_id: int,
        media_id: int,
        *,
        tag: str | None = None,
        position: int = 0,
    ) -> ServiceAttachmentModel:
        att = ServiceAttachmentModel(
            service_id=service_id, media_id=media_id, tag=tag, position=position
        )
        self.s.add(att)
        await self.s.flush()
        return att

    async def remove(self, att_id: int) -> None:
        att = await self.by_id(att_id)
        if att is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
        await self.s.delete(att)
        await self.s.flush()

    async def clear_service(self, service_id: int) -> None:
        await self.s.execute(
            delete(ServiceAttachmentModel).where(
                ServiceAttachmentModel.service_id == service_id
            )
        )


__all__ = ["ServiceAttachmentModel", "ServiceAttachmentMngr"]
