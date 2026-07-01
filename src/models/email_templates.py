"""Email-шаблоны (EmailModel) + менеджер (EmailMngr)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now


class EmailModel(Base):
    """Шаблон письма (тема + тело-файл jinja2)."""

    __tablename__ = "email_templates"

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

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Тема письма как jinja2-строка (может содержать переменные контекста).
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Имя файла тела относительно EMAIL_TEMPLATES_DIR (генерируется системой).
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Тело — HTML (True) или текст (False).
    is_html: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EmailMngr:
    """Регистрация и хранение email-шаблонов в монтируемой папке."""

    def __init__(self, session: AsyncSession, templates_dir: str) -> None:
        self.s = session
        self.dir = Path(templates_dir)

    async def list_all(self) -> list[EmailModel]:
        rows = await self.s.scalars(select(EmailModel).order_by(EmailModel.id))
        return list(rows)

    async def by_slug(self, slug: str) -> EmailModel | None:
        return await self.s.scalar(select(EmailModel).where(EmailModel.slug == slug))

    async def by_id(self, tpl_id: int) -> EmailModel | None:
        return await self.s.get(EmailModel, tpl_id)

    def _gen_filename(self) -> str:
        """Сгенерировать безопасное имя файла тела шаблона."""
        return f"{uuid.uuid4().hex}.j2"

    def _safe_target(self, filename: str) -> Path:
        target = (self.dir / filename).resolve()
        if not str(target).startswith(str(self.dir.resolve())):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый путь файла")
        return target

    async def create(self, data) -> EmailModel:  # noqa: ANN001 — schemas.EmailUpload
        """Сохранить тело шаблона в файл и зарегистрировать запись."""
        if await self.by_slug(data.slug):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug шаблона занят")

        filename = self._gen_filename()
        target = self._safe_target(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data.body, encoding="utf-8")

        row = EmailModel(
            slug=data.slug,
            name=data.name,
            subject=data.subject,
            filename=filename,
            is_html=data.is_html,
            sha256=hashlib.sha256(data.body.encode()).hexdigest(),
            description=data.description,
        )
        self.s.add(row)
        await self.s.flush()
        return row

    async def update_body(self, tpl_id: int, body: str) -> EmailModel:
        """Перезаписать тело существующего шаблона."""
        row = await self.by_id(tpl_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "шаблон не найден")
        target = self._safe_target(row.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        row.sha256 = hashlib.sha256(body.encode()).hexdigest()
        await self.s.flush()
        return row

    async def patch(self, tpl_id: int, data) -> EmailModel:  # noqa: ANN001
        """Обновить визуальные поля шаблона (без тела)."""
        row = await self.by_id(tpl_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "шаблон не найден")
        for field in ("name", "subject", "is_html", "description", "is_active"):
            val = getattr(data, field, None)
            if val is not None:
                setattr(row, field, val)
        await self.s.flush()
        return row

    async def read_body(self, row: EmailModel) -> str:
        """Прочитать тело шаблона из файла."""
        target = self._safe_target(row.filename)
        if not target.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "файл тела шаблона отсутствует"
            )
        return target.read_text(encoding="utf-8")

    async def delete(self, tpl_id: int) -> None:
        """Удалить запись шаблона и его файл."""
        row = await self.by_id(tpl_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "шаблон не найден")
        target = self._safe_target(row.filename)
        if target.exists():
            target.unlink()
        await self.s.delete(row)
        await self.s.flush()


__all__ = ["EmailModel", "EmailMngr"]
