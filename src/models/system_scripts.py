"""Lua-скрипты системы (SystemScriptsModel) + менеджер (SystemScriptsMngr)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import ScriptKind
from utils.datetime_utils import utc_now

# Подпапка хранения по виду скрипта (внутри LUA_SCRIPTS_DIR).
_SUBDIR_BY_KIND = {
    ScriptKind.SERVICE: "services",
    ScriptKind.PAYMENT: "payments",
}


class SystemScriptsModel(Base):
    """Запись о Lua-скрипте."""

    __tablename__ = "lua_scripts"

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

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # service | payment | generic (см. ScriptKind).
    kind: Mapped[str] = mapped_column(
        String(16), default=ScriptKind.SERVICE, nullable=False
    )
    # Имя файла относительно LUA_SCRIPTS_DIR (генерируется системой, напр.
    # "services/3f9c1a....lua"). Клиент имя файла не задаёт.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # TODO: ограничить размер
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SystemScriptsMngr:
    """Регистрация и хранение Lua-скриптов в монтируемой папке."""

    def __init__(self, session: AsyncSession, scripts_dir: str) -> None:
        self.s = session
        self.dir = Path(scripts_dir)

    async def list_all(self) -> list[SystemScriptsModel]:
        rows = await self.s.scalars(
            select(SystemScriptsModel).order_by(SystemScriptsModel.id)
        )
        return list(rows)

    async def by_slug(self, slug: str) -> SystemScriptsModel | None:
        return await self.s.scalar(
            select(SystemScriptsModel).where(SystemScriptsModel.slug == slug)
        )

    def _gen_filename(self, kind: str) -> str:
        """Сгенерировать безопасное имя файла скрипта (uuid4 + подпапка по виду)."""
        subdir = _SUBDIR_BY_KIND.get(kind, "generic")
        return f"{subdir}/{uuid.uuid4().hex}.lua"

    async def create(self, data) -> SystemScriptsModel:
        """Записать тело скрипта в файл со сгенерированным именем и сохранить карту."""
        if await self.by_slug(data.slug):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug скрипта занят")

        filename = self._gen_filename(data.kind)
        target = self._safe_target(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data.code, encoding="utf-8")

        row = SystemScriptsModel(
            slug=data.slug,
            name=data.name,
            kind=data.kind,
            filename=filename,
            sha256=hashlib.sha256(data.code.encode()).hexdigest(),
            description=data.description,
        )
        self.s.add(row)
        await self.s.flush()
        return row

    async def by_id(self, script_id: int) -> SystemScriptsModel | None:
        return await self.s.get(SystemScriptsModel, script_id)

    def _safe_target(self, filename: str) -> Path:
        target = (self.dir / filename).resolve()
        if not str(target).startswith(str(self.dir.resolve())):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый путь файла")
        return target

    async def update_code(self, script_id: int, code: str) -> SystemScriptsModel:
        """Перезаписать тело существующего скрипта."""
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "скрипт не найден")
        target = self._safe_target(row.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        row.sha256 = hashlib.sha256(code.encode()).hexdigest()
        await self.s.flush()
        return row

    async def delete(self, script_id: int) -> None:
        """Удалить запись скрипта и его файл."""
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "скрипт не найден")
        target = self._safe_target(row.filename)
        if target.exists():
            target.unlink()
        await self.s.delete(row)
        await self.s.flush()


__all__ = ["SystemScriptsModel", "SystemScriptsMngr"]
