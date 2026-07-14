"""Системные медиа-файлы (SystemMediaModel) + менеджер (SystemMediaMngr)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, DateTime, Integer, JSON, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


def _gen_token() -> str:
    """Публичный идентификатор медиа (он же file_id и task_token)."""
    return uuid.uuid4().hex


class SystemMediaModel(Base):
    """Медиа-файл системы (изображение, иконка, аватар и т.п.).

    Файлы физически хранит и отдаёт mediaworker; здесь — только метаданные.
    ``token`` — публичный идентификатор в URL ``/api/media/{token}`` (и task_token
    конверсии). ``path`` для fs — относительный ключ в ``data/media`` (напр.
    ``{token}.webp``), для s3 — ключ объекта.
    """

    __tablename__ = "system_media"

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

    token: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=_gen_token, nullable=False
    )
    # processing | ready | failed
    status: Mapped[str] = mapped_column(
        String(16), default="ready", server_default="ready", nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # image/video/icon/avatar
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # fs key or s3 key
    backend: Mapped[str] = mapped_column(String(8), default="fs", nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )  # uploader account id
    # Метка для UI (админка/клиент) — до 16 символов, латиница+цифры, задаётся
    # при загрузке (необязательно) и может быть изменена позже. Не влияет на
    # обработку файла (в отличие от прежнего kind, который клиент заявлял сам).
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Варианты файла: {"main": {...}, "preview": {...}, "preview_thumb": {...}}
    # (для фото — только "main", отдельный thumb не генерируется).
    # Каждый — {"key", "mime", "size", "url"}. Заполняет mediaworker.
    variants: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    meta: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )


class SystemMediaMngr:
    """CRUD для системных медиа-файлов."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, media_id: int) -> SystemMediaModel | None:
        return await self.s.get(SystemMediaModel, media_id)

    async def by_token(self, token: str) -> SystemMediaModel | None:
        return await self.s.scalar(
            select(SystemMediaModel).where(SystemMediaModel.token == token)
        )

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
        token: str | None = None,
        status: str = "ready",
        backend: str = "fs",
        mime: str | None = None,
        size: int | None = None,
        owner_id: int | None = None,
        variants: dict | None = None,
        meta: dict | None = None,
        tag: str | None = None,
    ) -> SystemMediaModel:
        media = SystemMediaModel(
            kind=kind,
            path=path,
            backend=backend,
            mime=mime,
            size=size,
            owner_id=owner_id,
            variants=variants or {},
            meta=meta or {},
            status=status,
            tag=tag,
            **({"token": token} if token else {}),
        )
        self.s.add(media)
        await self.s.flush()
        return media

    async def delete(self, media: SystemMediaModel) -> None:
        """Удалить запись медиа из БД (файл удаляет mediaworker отдельно)."""
        await self.s.delete(media)
        await self.s.flush()

    async def upsert(
        self,
        *,
        token: str,
        kind: str,
        path: str,
        backend: str = "fs",
        mime: str | None = None,
        size: int | None = None,
        owner_id: int | None = None,
        variants: dict | None = None,
        status: str = "ready",
        tag: str | None = None,
    ) -> SystemMediaModel:
        """Идемпотентно записать готовое медиа по ``token`` (insert или update).

        Используется консьюмером результатов конвертации (mediaworker → billing):
        логика записи в БД живёт только здесь, в одном сервисе.
        """
        media = await self.by_token(token)
        if media is None:
            return await self.create(
                kind,
                path,
                token=token,
                status=status,
                backend=backend,
                mime=mime,
                size=size,
                owner_id=owner_id,
                variants=variants or {},
                tag=tag,
            )
        media.kind = kind
        media.path = path
        media.backend = backend
        media.mime = mime
        media.size = size
        if owner_id is not None:
            media.owner_id = owner_id
        media.variants = variants or {}
        media.status = status
        if tag is not None:
            media.tag = tag
        await self.s.flush()
        return media

    async def set_tag(self, media: SystemMediaModel, tag: str | None) -> None:
        """Изменить метку медиа (админка/клиент) — не влияет на файл/конверсию."""
        media.tag = tag
        await self.s.flush()

    async def merge_variants(self, token: str, variants: dict) -> None:
        """Домержить набор вариантов к существующей записи (ручное превью)."""
        media = await self.by_token(token)
        if media is None:
            return
        media.variants = {**(media.variants or {}), **variants}
        await self.s.flush()

    async def orphans(self, grace_sec: int = 3600) -> list[SystemMediaModel]:
        """Медиа, не привязанные ни к товарам (attachments), ни к аватаркам.

        :arg grace_sec: не рассматривать кандидатами записи младше этого
            порога (секунды от создания) — грейс-период против TOCTOU: файл,
            только что загруженный и ещё не успевший привязаться к сущности
            (или ещё обрабатываемый mediaworker'ом), не удаляется в текущем
            проходе, будет учтён в следующем, если действительно осиротел
            (см. IMPLEMENTATION_PLAN §11.3).
        :return: список «осиротевших» записей для чистки.
        """
        from models.service_attachment import ServiceAttachmentModel
        from models.user import UserModel

        used_att = select(ServiceAttachmentModel.media_id)
        used_avatar = select(UserModel.avatar_media_id).where(
            UserModel.avatar_media_id.is_not(None)
        )
        cutoff = utc_now() - timedelta(seconds=grace_sec)
        rows = await self.s.scalars(
            select(SystemMediaModel)
            .where(SystemMediaModel.id.not_in(used_att))
            .where(SystemMediaModel.id.not_in(used_avatar))
            .where(SystemMediaModel.created_at < cutoff)
            .order_by(SystemMediaModel.id)
        )
        return list(rows)


__all__ = ["SystemMediaModel", "SystemMediaMngr"]
