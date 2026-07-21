"""Системные медиа-файлы (SystemMediaModel) + менеджер (SystemMediaMngr)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, DateTime, Integer, JSON, Select, String, select
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
    )
    # Метка для UI (админка/клиент) — до 16 символов, латиница+цифры.
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
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
        rows = await self.s.scalars(self.stmt_for_owner(owner_id))
        return list(rows)

    def stmt_for_owner(self, owner_id: int) -> Select:
        """Базовый select медиа владельца (для пагинации, см. utils/pagination)."""
        return (
            select(SystemMediaModel)
            .where(SystemMediaModel.owner_id == owner_id)
            .order_by(SystemMediaModel.id.desc())
        )

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
        meta: dict | None = None,
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
                meta=meta or {},
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
        if meta is not None:
            media.meta = meta
        media.status = status
        if tag is not None:
            media.tag = tag
        await self.s.flush()
        return media

    async def set_tag(self, media: SystemMediaModel, tag: str | None) -> None:
        """Изменить метку медиа (админка/клиент) — не влияет на файл/конверсию."""
        media.tag = tag
        await self.s.flush()

    async def _locked(self, token: str) -> SystemMediaModel | None:
        """Прочитать запись с блокировкой строки (``FOR UPDATE``).

        Нужно для операций, читающих-модифицирующих-пишущих JSON ``variants``
        (append/replace) — без блокировки два параллельных запроса на
        добавление превью могут потерять один из результатов.
        """
        return await self.s.scalar(
            select(SystemMediaModel)
            .where(SystemMediaModel.token == token)
            .with_for_update()
        )

    async def append_preview(self, token: str, preview: dict) -> None:
        """Добавить новое превью в конец ``previews[]`` (не трогая остальные)."""
        media = await self._locked(token)
        if media is None:
            return
        variants = dict(media.variants or {})
        previews = list(variants.get("previews") or [])
        previews.append(preview)
        variants["previews"] = previews
        media.variants = variants
        await self.s.flush()

    async def set_thumb(self, token: str, thumb: dict) -> dict | None:
        """Заменить ``thumb`` целиком; вернуть старый объект (для удаления файла)."""
        media = await self._locked(token)
        if media is None:
            return None
        variants = dict(media.variants or {})
        old = variants.get("thumb")
        variants["thumb"] = thumb
        media.variants = variants
        await self.s.flush()
        return old

    async def remove_preview(self, media: SystemMediaModel, index: int) -> dict | None:
        """Удалить превью по индексу; вернуть удалённый объект (для очистки файла)."""
        variants = dict(media.variants or {})
        previews = list(variants.get("previews") or [])
        if index < 0 or index >= len(previews):
            return None
        removed = previews.pop(index)
        variants["previews"] = previews
        media.variants = variants
        await self.s.flush()
        return removed

    async def reorder_previews(self, media: SystemMediaModel, order: list[int]) -> bool:
        """Переставить ``previews[]`` по новому порядку индексов.

        :arg order: перестановка индексов текущего списка (та же длина, тот
            же набор значений — иначе ``False`` без изменений).
        """
        variants = dict(media.variants or {})
        previews = list(variants.get("previews") or [])
        if sorted(order) != list(range(len(previews))):
            return False
        variants["previews"] = [previews[i] for i in order]
        media.variants = variants
        await self.s.flush()
        return True

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


def all_storage_keys(media: SystemMediaModel) -> list[str]:
    """Ключи ВСЕХ физических файлов медиа: main + thumb + previews[].

    ``media.path`` — это только ключ main-варианта. ``thumb`` и ``previews``
    — отдельные файлы в хранилище, их ключи лежат в ``media.variants``.
    Использовать при полном удалении медиа (иначе thumb/previews остаются
    висеть в хранилище мусором навсегда — запись в БД уже удалена, и
    ``orphans()`` их найти больше не сможет).
    """
    keys = [media.path]
    # getattr — тесты передают облегчённые SimpleNamespace-заглушки без
    # variants (старые медиа без вариантов); полноценный ORM-объект тоже
    # покрыт, ``variants`` там по умолчанию непустой dict, не None.
    variants = getattr(media, "variants", None) or {}
    thumb = variants.get("thumb")
    if thumb and thumb.get("key"):
        keys.append(thumb["key"])
    for preview in variants.get("previews") or []:
        if preview and preview.get("key"):
            keys.append(preview["key"])
    return keys


__all__ = ["SystemMediaModel", "SystemMediaMngr", "all_storage_keys"]
