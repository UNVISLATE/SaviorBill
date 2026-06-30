"""Схемы Lua-скриптов (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaScript(BaseModel):
    """Зарегистрированный Lua-скрипт (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    filename: str
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "LuaScript":  # noqa: ANN001 — SystemScriptsModel
        """Явное преобразование ORM-скрипта в схему ответа."""
        return cls.model_validate(m)


class LuaScriptUpload(BaseModel):
    """Регистрация нового Lua-скрипта.

    Имя файла на диске генерируется системой (клиент его не задаёт). ``name`` —
    только для отображения в админке.
    """

    slug: str = Field(min_length=2, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    kind: str = Field(default="service", description="service | payment | generic")
    code: str = Field(description="Тело Lua-скрипта (модуль с функцией handle(ctx))")
    description: str | None = Field(default=None, max_length=2048)


class LuaScriptPatch(BaseModel):
    """Замена тела существующего Lua-скрипта."""

    code: str = Field(description="Новое тело Lua-скрипта")


__all__ = [
    "LuaScript",
    "LuaScriptUpload",
    "LuaScriptPatch",
]
