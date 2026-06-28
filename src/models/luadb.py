"""Карта Lua-скриптов: связь id <-> файл в монтируемой папке."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import ScriptKind
from orm.mixins import PkMixin, TsMixin


class LuaScript(PkMixin, TsMixin, Base):
    """Запись о Lua-скрипте.

    Сам код лежит в монтируемой папке (``LUA_SCRIPTS_DIR``) под именем
    ``filename`` — её видят и ядро (rw, для загрузки новых), и LuaWorker (ro,
    для исполнения). В БД хранится карта: id/slug -> файл + метаданные.
    """

    __tablename__ = "lua_scripts"

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # service | payment | generic (см. ScriptKind).
    kind: Mapped[str] = mapped_column(String(16), default=ScriptKind.SERVICE, nullable=False)
    # Имя файла относительно LUA_SCRIPTS_DIR (например "services/demo.lua").
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = ["LuaScript"]
